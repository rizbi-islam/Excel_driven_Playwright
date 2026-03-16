"""
app/core/http_client.py — Production-grade HTTP request sender.

Body types supported:
  none         → no body (GET, DELETE, HEAD etc.)
  json         → application/json
  form         → application/x-www-form-urlencoded  (key=value&key2=value2)
  multipart    → multipart/form-data  (KV dict with proper boundary)
  xml          → application/xml
  graphql      → application/json  (wraps query string)
  raw          → text/plain (or whatever Content-Type caller sets)

Default browser User-Agent prevents Cloudflare/WAF 403 error 1010.
"""
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

STATUS_TEXTS = {
    200: "OK", 201: "Created", 202: "Accepted", 204: "No Content",
    301: "Moved Permanently", 302: "Found", 304: "Not Modified",
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
    404: "Not Found", 405: "Method Not Allowed", 408: "Request Timeout",
    409: "Conflict", 415: "Unsupported Media Type",
    422: "Unprocessable Entity", 429: "Too Many Requests",
    500: "Internal Server Error", 502: "Bad Gateway",
    503: "Service Unavailable", 504: "Gateway Timeout",
}

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class HttpClient:

    @staticmethod
    def send(
        method:           str,
        url:              str,
        headers:          dict = None,
        params:           dict = None,
        body_type:        str  = "none",
        body:             Any  = None,
        timeout:          int  = 30,
        follow_redirects: bool = True,
    ) -> dict:
        if not url or not url.startswith(("http://", "https://")):
            return HttpClient._err("URL must start with http:// or https://")

        method  = (method or "GET").upper()
        headers = dict(headers or {})
        params  = {k: v for k, v in (params or {}).items()
                   if k is not None and v is not None}

        # Browser-like defaults — prevents Cloudflare 403 error 1010
        headers.setdefault("User-Agent",      _DEFAULT_UA)
        headers.setdefault("Accept",          "*/*")
        headers.setdefault("Accept-Language", "en-US,en;q=0.9")

        # Append query params to URL
        if params:
            qs  = urllib.parse.urlencode(params, doseq=True)
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{qs}"

        # Build request body bytes
        data: bytes | None = None
        try:
            data = HttpClient._build_body(body_type, body, headers)
        except Exception as exc:
            return HttpClient._err(f"Body encoding failed: {exc}")

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode    = ssl.CERT_NONE

        req    = urllib.request.Request(url, data=data, headers=headers, method=method)
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl_ctx),
            urllib.request.HTTPRedirectHandler() if follow_redirects
            else _NoRedirectHandler(),
        )

        start = time.perf_counter()
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                ms  = round((time.perf_counter() - start) * 1000, 2)
                return HttpClient._build_response(resp, raw, ms)

        except urllib.error.HTTPError as exc:
            ms = round((time.perf_counter() - start) * 1000, 2)
            try:    raw = exc.read()
            except: raw = b""
            return HttpClient._build_response(exc, raw, ms)

        except urllib.error.URLError as exc:
            ms  = round((time.perf_counter() - start) * 1000, 2)
            r   = str(exc.reason) if exc.reason else str(exc)
            rl  = r.lower()
            if   "connection refused"         in rl: msg = f"Connection refused — is the server running?"
            elif "name or service not known"  in rl: msg = f"DNS lookup failed: {url}"
            elif "nodename nor servname"      in rl: msg = f"DNS lookup failed: {url}"
            elif "timed out"                  in rl: msg = f"Request timed out after {timeout}s"
            elif "ssl"                        in rl: msg = f"SSL/TLS error: {r}"
            else:                                    msg = f"Network error: {r}"
            return HttpClient._err(msg, ms)

        except TimeoutError:
            ms = round((time.perf_counter() - start) * 1000, 2)
            return HttpClient._err(f"Request timed out after {timeout}s", ms)

        except Exception as exc:
            ms = round((time.perf_counter() - start) * 1000, 2)
            return HttpClient._err(str(exc), ms)

    # ── Body builder ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_body(body_type: str, body: Any, headers: dict) -> bytes | None:
        if body_type == "none" or body is None:
            return None

        # ── JSON ──────────────────────────────────────────────────────────────
        if body_type == "json":
            payload = json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body
            headers.setdefault("Content-Type", "application/json; charset=utf-8")
            return payload.encode("utf-8")

        # ── form-urlencoded ───────────────────────────────────────────────────
        if body_type in ("form", "urlencoded"):
            if isinstance(body, dict):
                payload = urllib.parse.urlencode(
                    {k: v for k, v in body.items() if k}, doseq=True
                )
            else:
                payload = str(body)
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            return payload.encode("utf-8")

        # ── multipart/form-data ───────────────────────────────────────────────
        # body must be a dict: {"key": "value", ...}
        if body_type == "multipart":
            boundary = f"----FormBoundary{os.urandom(12).hex()}"
            parts    = []
            items    = body.items() if isinstance(body, dict) else []
            for key, value in items:
                if key is None:
                    continue
                val_str = str(value) if value is not None else ""
                parts.append(
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{key}"\r\n'
                    f"\r\n"
                    f"{val_str}\r\n"
                )
            parts.append(f"--{boundary}--\r\n")
            payload = "".join(parts).encode("utf-8")
            # Force set (do not setdefault — multipart boundary MUST be exact)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            return payload

        # ── XML ───────────────────────────────────────────────────────────────
        if body_type == "xml":
            text = body if isinstance(body, str) else json.dumps(body)
            headers.setdefault("Content-Type", "application/xml; charset=utf-8")
            return text.encode("utf-8")

        # ── GraphQL ───────────────────────────────────────────────────────────
        if body_type == "graphql":
            if isinstance(body, dict):
                payload = json.dumps(body)
            else:
                payload = json.dumps({"query": str(body)})
            headers.setdefault("Content-Type", "application/json")
            return payload.encode("utf-8")

        # ── raw / text ────────────────────────────────────────────────────────
        text = body if isinstance(body, str) else json.dumps(body)
        headers.setdefault("Content-Type", "text/plain; charset=utf-8")
        return text.encode("utf-8")

    # ── Response builder ──────────────────────────────────────────────────────

    @staticmethod
    def _build_response(resp, raw: bytes, elapsed_ms: float) -> dict:
        status = getattr(resp, "status", None) or getattr(resp, "code", 0) or 0

        resp_headers: dict[str, str] = {}
        try:
            for k, v in resp.headers.items():
                resp_headers[k.lower()] = v
        except Exception:
            pass

        charset = "utf-8"
        ct = resp_headers.get("content-type", "")
        if "charset=" in ct:
            charset = ct.split("charset=")[-1].split(";")[0].strip()
        try:    body_text = raw.decode(charset, errors="replace")
        except: body_text = raw.decode("utf-8", errors="replace")

        # Pretty-print JSON
        try:    body_text = json.dumps(json.loads(body_text), indent=2, ensure_ascii=False)
        except: pass

        return {
            "ok":           status < 400,
            "status":       status,
            "status_text":  STATUS_TEXTS.get(status, "Unknown"),
            "response_ms":  elapsed_ms,
            "size":         len(raw),
            "body":         body_text,
            "resp_headers": resp_headers,
            "error":        None,
            "redirects":    0,
        }

    @staticmethod
    def _err(msg: str, elapsed_ms: float = 0) -> dict:
        return {
            "ok":           False,
            "status":       0,
            "status_text":  "Error",
            "response_ms":  elapsed_ms,
            "size":         0,
            "body":         "",
            "resp_headers": {},
            "error":        msg,
            "redirects":    0,
        }


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None
