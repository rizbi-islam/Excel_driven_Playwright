"""
app/core/runner.py — Central test execution orchestrator.
Dispatches to the correct engine. APIs with no body/params are fully supported.
"""
import json
import time

from app.core.http_client    import HttpClient
from app.database.models.run import ResultModel


def run_cases(cases: list, base_url: str, test_type: str,
              run_id: int, owner_id: int, **kwargs) -> dict:
    """
    Dispatch to the right engine.
    kwargs: concurrency, duration_sec, start_users, peak_users, ramp_sec
    """
    if test_type == "load":
        from app.core.engines.load_engine import run_load
        return run_load(
            cases, base_url, run_id, owner_id,
            concurrency  = int(kwargs.get("concurrency") or 10),
            duration_sec = int(kwargs.get("duration_sec") or 30),
        )

    if test_type == "stress":
        from app.core.engines.load_engine import run_stress
        return run_stress(
            cases, base_url, run_id, owner_id,
            start_users = int(kwargs.get("start_users") or 1),
            peak_users  = int(kwargs.get("peak_users") or 50),
            ramp_sec    = int(kwargs.get("ramp_sec") or 60),
        )

    if test_type == "security":
        from app.core.engines.security_engine import run_security
        return run_security(cases, base_url, run_id, owner_id)

    # smoke | regression — sequential
    return _run_sequential(cases, base_url, test_type, run_id, owner_id)


# ── Sequential runner ─────────────────────────────────────────────────────────

def _run_sequential(cases, base_url, test_type, run_id, owner_id) -> dict:
    total = passed = failed = 0
    start = time.perf_counter()

    for case in cases:
        result = _run_single(case, base_url)
        result["test_type"]    = test_type
        result["request_data"] = _case_snapshot(case)
        ResultModel.save(run_id, owner_id, result)
        total += 1
        if result["status"] == "PASS":
            passed += 1
        else:
            failed += 1

    duration = round(time.perf_counter() - start, 2)
    return dict(
        total    = total,
        passed   = passed,
        failed   = failed,
        duration = duration,
        pass_rate = round(passed / total * 100, 1) if total else 0,
    )


def _run_single(case: dict, base_url: str) -> dict:
    method   = (case.get("method") or "GET").upper()
    endpoint = case.get("endpoint", "")
    url      = (endpoint if endpoint.startswith("http")
                else f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}")

    headers = dict(case.get("headers") or {})
    params  = dict(case.get("params")  or {})
    body    = case.get("body")

    # Apply auth
    auth_type = case.get("auth_type", "none")
    auth_tok  = case.get("auth_token", "")
    if auth_type == "bearer" and auth_tok:
        headers["Authorization"] = f"Bearer {auth_tok}"
    elif auth_type == "basic" and auth_tok:
        headers["Authorization"] = f"Basic {auth_tok}"
    elif auth_type == "apikey" and auth_tok:
        headers["X-API-Key"] = auth_tok

    # body=None → body_type="none" → no body sent (correct for GET/DELETE/HEAD etc.)
    body_type = "json" if body is not None else "none"

    resp = HttpClient.send(
        method=method, url=url, headers=headers, params=params,
        body_type=body_type, body=body, timeout=30,
    )

    expected = int(case.get("expected_status") or 200)
    ok       = resp["status"] == expected

    assertions = []
    for a in (case.get("assertions") or []):
        ar = _check_assertion(a, resp)
        assertions.append(ar)
        if not ar["passed"]:
            ok = False

    max_ms = case.get("max_response_ms")
    if max_ms and resp["response_ms"] > int(max_ms):
        ok = False
        assertions.append({
            "type": "response_time", "passed": False,
            "expected": f"<={max_ms}ms", "actual": f"{resp['response_ms']}ms",
        })

    return {
        "name":            case.get("name", endpoint),
        "method":          method,
        "endpoint":        url,
        "status":          "PASS" if ok else "FAIL",
        "actual_status":   resp["status"],
        "expected_status": expected,
        "response_ms":     resp["response_ms"],
        "response_body":   resp["body"],
        "resp_headers":    resp["resp_headers"],
        "assertions":      assertions,
        "error":           resp.get("error"),
    }


def _check_assertion(a: dict, resp: dict) -> dict:
    a_type   = a.get("type", "")
    expected = a.get("expected", "")
    actual   = ""
    ok       = False

    try:
        if a_type == "status_code":
            actual = str(resp["status"])
            ok     = actual == str(expected)

        elif a_type == "body_contains":
            actual = "(body)"
            ok     = str(expected) in resp.get("body", "")

        elif a_type == "body_json_path":
            path  = a.get("path", "")
            body  = json.loads(resp.get("body", "{}"))
            val   = body
            for p in path.split("."):
                val = val[p] if isinstance(val, dict) else val[int(p)]
            actual = str(val)
            ok     = actual == str(expected)

        elif a_type == "header_exists":
            actual = resp["resp_headers"].get(str(expected).lower(), "")
            ok     = str(expected).lower() in resp.get("resp_headers", {})

        elif a_type == "response_time":
            actual = f"{resp['response_ms']}ms"
            ok     = resp["response_ms"] <= float(expected)

    except Exception as exc:
        actual = f"Error: {exc}"
        ok     = False

    return {"type": a_type, "expected": str(expected), "actual": actual, "passed": ok}


def _case_snapshot(case: dict) -> dict:
    """Safe serialisable copy of a case for request_data column."""
    return {k: v for k, v in case.items() if k in (
        "name", "method", "endpoint", "headers", "body", "params",
        "expected_status", "auth_type", "auth_token", "max_response_ms",
        "assertions", "tags", "description", "sheet_type", "test_type",
    )}


# ── Batch / parameterized expansion ──────────────────────────────────────────

def expand_batch(params: dict, body) -> list[tuple[dict, object]]:
    """
    If any param value OR body key contains a list, expand it.
    Returns list of (params, body) tuples — one per value.
    Limited to first array found (params take priority).
    Max 50 combinations.
    """
    # Check params first
    for k, v in (params or {}).items():
        arr = None
        if isinstance(v, list):
            arr = v
        elif isinstance(v, str) and v.strip().startswith("["):
            try:    arr = json.loads(v.strip())
            except: pass
        if arr is not None:
            return [({**params, k: item}, body) for item in arr[:50]]

    # Check body dict
    if isinstance(body, dict):
        for k, v in body.items():
            if isinstance(v, list):
                return [(params, {**body, k: item}) for item in v[:50]]

    # No expansion
    return [(params, body)]
