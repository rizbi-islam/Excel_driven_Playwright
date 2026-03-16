"""
app/core/engines/security_engine.py — Automated security checks.
Checks: HTTPS, CORS, Auth Bypass, SQL Injection, XSS, Info Disclosure, Rate Limit headers.
"""
import time

from app.core.http_client        import HttpClient
from app.database.models.run     import SecurityFindingModel

SQL_PAYLOADS  = ["' OR '1'='1", "'; DROP TABLE users--", "1 OR 1=1", "\" OR \"\"=\""]
XSS_PAYLOADS  = ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "javascript:alert(1)"]
SQL_ERRORS    = ["sql syntax","mysql_fetch","sqlite_","ora-0","pg_query","syntax error",
                 "database error","unclosed quotation","you have an error in your sql"]
TECH_HEADERS  = ["server","x-powered-by","x-aspnet-version","x-aspnetmvc-version",
                 "x-runtime","x-version","x-generator"]
ALL_CHECKS    = ["https","cors","auth_bypass","sqli","xss","info_disclosure","rate_limit"]


def _url(base_url: str, endpoint: str) -> str:
    return (endpoint if endpoint.startswith("http")
            else f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}")


def _req(method, url, headers=None, params=None, body=None, timeout=10) -> dict:
    bt = "json" if body is not None else "none"
    return HttpClient.send(method=method, url=url, headers=dict(headers or {}),
                           params=dict(params or {}), body_type=bt, body=body, timeout=timeout)


def _f(endpoint, check, severity, passed, finding, detail="") -> dict:
    return dict(endpoint=endpoint, check_type=check, severity=severity,
                passed=passed, finding=finding, detail=detail)


def _check_https(url: str, ep: str) -> list:
    if url.startswith("http://"):
        return [_f(ep, "https", "high", False,
                   "HTTP used instead of HTTPS — data in transit unencrypted.")]
    return [_f(ep, "https", "info", True, "HTTPS in use — transport is encrypted.")]


def _check_cors(url: str, ep: str, base_headers: dict) -> list:
    h    = {**base_headers, "Origin": "https://evil-attacker.com"}
    resp = _req("GET", url, headers=h)
    acao = resp["resp_headers"].get("access-control-allow-origin", "")
    if acao == "*":
        return [_f(ep, "cors", "medium", False,
                   "CORS allows all origins (*).",
                   "Access-Control-Allow-Origin: * permits any domain to call this endpoint.")]
    if "evil-attacker.com" in acao:
        return [_f(ep, "cors", "high", False,
                   "CORS reflects arbitrary Origin header.",
                   f"Server echoed injected origin: {acao}")]
    return [_f(ep, "cors", "info", True, "CORS policy is restricted.")]


def _check_auth_bypass(method: str, url: str, ep: str,
                        headers: dict, params: dict, body) -> list:
    stripped = {k: v for k, v in headers.items()
                if k.lower() not in ("authorization", "x-api-key", "x-auth-token")}
    resp = _req(method, url, headers=stripped, params=params, body=body)
    if resp["status"] == 200:
        return [_f(ep, "auth_bypass", "critical", False,
                   "Endpoint accessible without authentication.",
                   f"Unauthenticated request returned HTTP {resp['status']}.")]
    if resp["status"] in (401, 403):
        return [_f(ep, "auth_bypass", "info", True,
                   f"Correctly returns HTTP {resp['status']} without auth.")]
    return [_f(ep, "auth_bypass", "low", False,
               f"Unexpected HTTP {resp['status']} without auth — review manually.")]


def _check_sqli(method: str, url: str, ep: str, params: dict, body) -> list:
    for payload in SQL_PAYLOADS[:2]:
        test_params = {**params, "id": payload, "search": payload, "q": payload}
        resp        = _req(method, url, params=test_params)
        body_lower  = resp["body"].lower()
        if any(e in body_lower for e in SQL_ERRORS):
            return [_f(ep, "sqli", "critical", False,
                       "SQL injection indicator — DB error message in response.",
                       f"Payload used: {payload!r}")]
        if resp["status"] == 500:
            return [_f(ep, "sqli", "medium", False,
                       "HTTP 500 on SQL payload — possible injection vector.",
                       f"Payload used: {payload!r}")]
    return [_f(ep, "sqli", "info", True, "No SQL injection indicators detected.")]


def _check_xss(method: str, url: str, ep: str, params: dict) -> list:
    payload     = XSS_PAYLOADS[0]
    test_params = {**params, "q": payload, "search": payload, "input": payload}
    resp        = _req(method, url, params=test_params)
    if payload in resp["body"]:
        return [_f(ep, "xss", "high", False,
                   "XSS payload reflected unescaped in response body.",
                   f"Payload {payload!r} found unmodified in response.")]
    return [_f(ep, "xss", "info", True, "No reflected XSS detected.")]


def _check_info_disclosure(url: str, ep: str) -> list:
    resp  = _req("GET", url)
    found = [h for h in TECH_HEADERS if h in resp["resp_headers"]]
    if found:
        vals = {h: resp["resp_headers"][h] for h in found}
        return [_f(ep, "info_disclosure", "low", False,
                   "Server exposes technology fingerprint headers.",
                   f"Headers present: {vals}")]
    body_lo = resp["body"].lower()
    if any(kw in body_lo for kw in ["traceback", "stack trace", "exception in", "at line "]):
        return [_f(ep, "info_disclosure", "medium", False,
                   "Stack trace or debug info in response body.")]
    return [_f(ep, "info_disclosure", "info", True,
               "No sensitive technology headers or stack traces detected.")]


def _check_rate_limit(url: str, ep: str, headers: dict) -> list:
    resp = _req("GET", url, headers=headers)
    rl   = [h for h in resp["resp_headers"]
            if "ratelimit" in h or "rate-limit" in h or "retry-after" in h]
    if not rl:
        return [_f(ep, "rate_limit", "low", False,
                   "No rate-limit headers detected.",
                   "Consider adding X-RateLimit-Limit / X-RateLimit-Remaining headers.")]
    return [_f(ep, "rate_limit", "info", True,
               f"Rate-limit headers present: {rl}")]


def run_security(cases: list, base_url: str, run_id: int, owner_id: int) -> dict:
    total = passed = failed = 0
    start = time.perf_counter()

    for case in cases:
        method    = (case.get("method") or "GET").upper()
        endpoint  = case.get("endpoint", "")
        url       = _url(base_url, endpoint)
        headers   = dict(case.get("headers") or {})
        params    = dict(case.get("params")  or {})
        body      = case.get("body")
        auth_type = case.get("auth_type", "none")
        auth_tok  = case.get("auth_token", "")

        if auth_type == "bearer" and auth_tok:
            headers["Authorization"] = f"Bearer {auth_tok}"
        elif auth_type == "basic" and auth_tok:
            headers["Authorization"] = f"Basic {auth_tok}"

        raw_checks = case.get("check_types") or ["all"]
        if isinstance(raw_checks, str):
            raw_checks = [c.strip() for c in raw_checks.split(",") if c.strip()]
        checks = ALL_CHECKS if "all" in raw_checks else [c for c in raw_checks if c in ALL_CHECKS]

        findings = []
        if "https"           in checks: findings += _check_https(url, endpoint)
        if "cors"            in checks: findings += _check_cors(url, endpoint, headers)
        if "auth_bypass"     in checks: findings += _check_auth_bypass(method, url, endpoint, headers, params, body)
        if "sqli"            in checks: findings += _check_sqli(method, url, endpoint, params, body)
        if "xss"             in checks: findings += _check_xss(method, url, endpoint, params)
        if "info_disclosure" in checks: findings += _check_info_disclosure(url, endpoint)
        if "rate_limit"      in checks: findings += _check_rate_limit(url, endpoint, headers)

        for f in findings:
            SecurityFindingModel.save(run_id, owner_id, f)
            total  += 1
            passed += 1 if f["passed"] else 0
            failed += 0 if f["passed"] else 1

    duration = round(time.perf_counter() - start, 2)
    return dict(total=total, passed=passed, failed=failed, duration=duration,
                pass_rate=round(passed / total * 100, 1) if total else 0)
