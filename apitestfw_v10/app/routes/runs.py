"""
app/routes/runs.py — Load, Stress, Security run pages.

Load/Stress: just need a base URL + endpoint list. No test cases required.
You give it URLs to hammer. Optionally pull from library.

Security: generate cases inline → review → run → optionally store.

Smoke/Regression: removed per user request — use library page instead.
"""
import json
import threading

from flask import Blueprint, render_template, request, jsonify

from app.auth.decorators             import login_required, require_page, get_current_user
from app.core.runner                 import run_cases
from app.core.http_client            import HttpClient
from app.database.models.api_model   import ApiModel
from app.database.models.environment import EnvironmentModel
from app.database.models.run         import (RunModel, ResultModel,
                                              LoadMetricModel, SecurityFindingModel)
from app.database.models.test_case   import TestCaseModel

bp = Blueprint("runs", __name__)


# ── Load page ─────────────────────────────────────────────────────

@bp.route("/run/load")
@login_required
@require_page("load")
def load_page():
    user = get_current_user()
    return render_template("run_load.html", user=user, pg="load",
                           apis=ApiModel.all_for_user(user["id"]),
                           envs=EnvironmentModel.all_for_user(user["id"]),
                           runs=RunModel.all_for_user(user["id"], test_type="load", limit=20))


# ── Stress page ───────────────────────────────────────────────────

@bp.route("/run/stress")
@login_required
@require_page("stress")
def stress_page():
    user = get_current_user()
    return render_template("run_stress.html", user=user, pg="stress",
                           apis=ApiModel.all_for_user(user["id"]),
                           envs=EnvironmentModel.all_for_user(user["id"]),
                           runs=RunModel.all_for_user(user["id"], test_type="stress", limit=20))


# ── Security page ─────────────────────────────────────────────────

@bp.route("/run/security")
@login_required
@require_page("security")
def security_page():
    user = get_current_user()
    return render_template("run_security.html", user=user, pg="security",
                           apis=ApiModel.all_for_user(user["id"]),
                           envs=EnvironmentModel.all_for_user(user["id"]),
                           runs=RunModel.all_for_user(user["id"], test_type="security", limit=20))


# ── Run Load (URL list, no test cases needed) ──────────────────────

@bp.route("/api/run/load", methods=["POST"])
@login_required
def api_run_load():
    """
    Body: {
      base_url, label?, api_id?,
      endpoints: [{method, path, body?, headers?, expected_status?}],
      concurrency: 10, duration_sec: 30
    }
    endpoints is optional — if empty, hammers base_url directly.
    """
    user        = get_current_user()
    d           = request.get_json(silent=True) or {}
    base_url    = (d.get("base_url") or "").strip().rstrip("/")
    label       =  d.get("label") or "load run"
    api_id      =  d.get("api_id")
    concurrency = max(1, min(int(d.get("concurrency") or 10), 200))
    duration    = max(5, min(int(d.get("duration_sec") or 30), 600))

    if not base_url:
        return jsonify(ok=False, error="base_url is required"), 400

    endpoints = d.get("endpoints") or []
    if not endpoints:
        # Default: hammer the base URL as-is
        endpoints = [{"method": "GET", "path": "", "expected_status": 200}]

    cases = _build_cases_from_endpoints(base_url, endpoints)
    run_id = RunModel.create(user["id"], api_id, label, base_url, "load",
                             source="excel", concurrency=concurrency)

    def _bg():
        try:
            from app.core.engines.load_engine import run_load
            summary = run_load(cases, base_url, run_id, user["id"],
                               concurrency=concurrency, duration_sec=duration)
            RunModel.finish(run_id, summary["total"], summary["passed"],
                            summary["failed"], summary["duration"])
        except Exception:
            RunModel.error(run_id)

    threading.Thread(target=_bg, daemon=True).start()
    return jsonify(ok=True, run_id=run_id, status="running",
                   endpoints=len(cases), concurrency=concurrency, duration_sec=duration)


# ── Run Stress (URL list, ramp up) ────────────────────────────────

@bp.route("/api/run/stress", methods=["POST"])
@login_required
def api_run_stress():
    user        = get_current_user()
    d           = request.get_json(silent=True) or {}
    base_url    = (d.get("base_url") or "").strip().rstrip("/")
    label       =  d.get("label") or "stress run"
    api_id      =  d.get("api_id")
    start_users = max(1, min(int(d.get("start_users") or 1), 50))
    peak_users  = max(start_users, min(int(d.get("peak_users") or 50), 200))
    ramp_sec    = max(10, min(int(d.get("ramp_sec") or 60), 600))

    if not base_url:
        return jsonify(ok=False, error="base_url is required"), 400

    endpoints = d.get("endpoints") or [{"method": "GET", "path": "", "expected_status": 200}]
    cases     = _build_cases_from_endpoints(base_url, endpoints)
    run_id    = RunModel.create(user["id"], api_id, label, base_url, "stress",
                                source="excel", concurrency=peak_users)

    def _bg():
        try:
            from app.core.engines.load_engine import run_stress
            summary = run_stress(cases, base_url, run_id, user["id"],
                                 start_users=start_users, peak_users=peak_users,
                                 ramp_sec=ramp_sec)
            RunModel.finish(run_id, summary["total"], summary["passed"],
                            summary["failed"], summary["duration"])
        except Exception:
            RunModel.error(run_id)

    threading.Thread(target=_bg, daemon=True).start()
    return jsonify(ok=True, run_id=run_id, status="running",
                   endpoints=len(cases), peak_users=peak_users)


# ── Security: generate cases ──────────────────────────────────────

@bp.route("/api/run/security/generate", methods=["POST"])
@login_required
def api_security_generate():
    """
    Probe endpoints and build security test cases (not stored yet).
    Returns list of cases user can review, toggle, then run or store.
    """
    d        = request.get_json(silent=True) or {}
    base_url = (d.get("base_url") or "").strip().rstrip("/")
    eps      = d.get("endpoints") or []
    auth_type= d.get("auth_type", "none")
    auth_tok = d.get("auth_token", "")

    if not base_url: return jsonify(ok=False, error="base_url required"), 400
    if not eps:      return jsonify(ok=False, error="At least one endpoint required"), 400

    hdrs: dict = {}
    if   auth_type == "bearer" and auth_tok: hdrs["Authorization"] = f"Bearer {auth_tok}"
    elif auth_type == "basic"  and auth_tok: hdrs["Authorization"] = f"Basic {auth_tok}"
    elif auth_type == "apikey" and auth_tok: hdrs["X-API-Key"]     = auth_tok

    from app.core.engines.security_engine import ALL_CHECKS
    cases = []
    for ep in eps:
        path   = (ep.get("path") or "").strip().lstrip("/")
        method = (ep.get("method") or "GET").upper()
        url    = f"{base_url}/{path}" if path else base_url

        # Quick probe to confirm endpoint exists
        probe = HttpClient.send(method="GET", url=url, headers=dict(hdrs),
                                body_type="none", timeout=10)

        cases.append({
            "name":            f"[Security] {method} /{path}" if path else f"[Security] {method} /",
            "method":          method,
            "endpoint":        f"/{path}" if path else "/",
            "headers":         dict(hdrs),
            "body":            ep.get("body"),
            "params":          ep.get("params") or {},
            "expected_status": int(ep.get("expected_status") or probe["status"] or 200),
            "auth_type":       auth_type,
            "auth_token":      auth_tok,
            "check_types":     ep.get("checks") or "all",
            "test_type":       "security",
            "sheet_type":      "security",
            "is_active":       True,
            "probe_status":    probe["status"],
            "probe_ok":        probe["ok"],
        })

    return jsonify(ok=True, cases=cases, base_url=base_url)


# ── Security: run cases ───────────────────────────────────────────

@bp.route("/api/run/security", methods=["POST"])
@login_required
def api_run_security():
    """
    Run security cases. Cases can come from:
      - inline 'cases' array (just generated)
      - library (active cases with sheet_type=security)
    Optionally stores cases to library if store=true.
    """
    user     = get_current_user()
    d        = request.get_json(silent=True) or {}
    base_url = (d.get("base_url") or "").strip().rstrip("/")
    label    =  d.get("label") or "security scan"
    api_id   =  d.get("api_id")
    cases    =  d.get("cases") or []
    store    =  bool(d.get("store_to_library", False))

    if not base_url: return jsonify(ok=False, error="base_url required"), 400

    # If no inline cases, pull from library
    if not cases:
        lib = TestCaseModel.all_for_user(user["id"], sheet_type="security")
        cases = [_row_to_dict(c) for c in lib if c.get("is_active", 1)]

    if not cases: return jsonify(ok=False, error="No security cases found"), 400

    # Optionally store cases to library first
    if store:
        for case in cases:
            case_data = dict(case)
            case_data["api_id"]    = int(api_id) if api_id else None
            case_data["is_active"] = 1
            try: TestCaseModel.save(user["id"], case_data)
            except Exception: pass

    run_id = RunModel.create(user["id"], api_id, label, base_url, "security",
                             source="excel", concurrency=1)

    def _bg():
        try:
            from app.core.engines.security_engine import run_security
            summary = run_security(cases, base_url, run_id, user["id"])
            RunModel.finish(run_id, summary["total"], summary["passed"],
                            summary["failed"], summary["duration"])
        except Exception:
            RunModel.error(run_id)

    threading.Thread(target=_bg, daemon=True).start()
    return jsonify(ok=True, run_id=run_id, status="running",
                   cases=len(cases), stored=store)


# ── Status / Results ──────────────────────────────────────────────

@bp.route("/api/run/<int:run_id>/status")
@login_required
def api_run_status(run_id):
    user = get_current_user()
    run  = RunModel.get(run_id, user["id"])
    if not run: return jsonify(ok=False, error="Not found"), 404
    return jsonify(ok=True, run={
        "id":           run["id"],
        "status":       run["status"],
        "total":        run["total"],
        "passed":       run["passed"],
        "failed":       run["failed"],
        "pass_rate":    float(run["pass_rate"] or 0),
        "duration_sec": float(run["duration_sec"] or 0),
        "test_type":    run["test_type"],
        "label":        run["label"],
    })


@bp.route("/api/run/<int:run_id>/results")
@login_required
def api_run_results(run_id):
    user     = get_current_user()
    run      = RunModel.get(run_id, user["id"])
    if not run: return jsonify(ok=False, error="Not found"), 404

    def safe(rows):
        out = []
        for r in rows:
            row = dict(r)
            for k, v in row.items():
                if hasattr(v, "isoformat"): row[k] = v.isoformat()
            out.append(row)
        return out

    return jsonify(ok=True,
                   run      = {k: (v.isoformat() if hasattr(v,"isoformat") else v)
                               for k, v in dict(run).items()},
                   results  = safe(ResultModel.for_run(run_id, user["id"])),
                   metrics  = safe(LoadMetricModel.for_run(run_id, user["id"])),
                   findings = safe(SecurityFindingModel.for_run(run_id, user["id"])))


# ── Helpers ───────────────────────────────────────────────────────

def _build_cases_from_endpoints(base_url: str, endpoints: list) -> list:
    """Build minimal test case dicts from a simple endpoint list."""
    cases = []
    for ep in endpoints:
        path   = (ep.get("path") or "").strip().lstrip("/")
        method = (ep.get("method") or "GET").upper()
        cases.append({
            "name":            ep.get("name") or (f"{method} /{path}" if path else f"{method} /"),
            "method":          method,
            "endpoint":        f"/{path}" if path else "/",
            "headers":         ep.get("headers") or {},
            "body":            ep.get("body"),
            "params":          ep.get("params") or {},
            "expected_status": int(ep.get("expected_status") or 200),
            "auth_type":       ep.get("auth_type", "none"),
            "auth_token":      ep.get("auth_token", ""),
        })
    return cases


def _row_to_dict(row) -> dict:
    case = dict(row)
    for fld in ("headers", "body", "params", "assertions", "tags"):
        v = case.get(fld)
        if isinstance(v, str):
            try:    case[fld] = json.loads(v)
            except: pass
        if case.get(fld) is None:
            case[fld] = {} if fld in ("headers", "params") else (
                        [] if fld in ("assertions", "tags") else None)
    return case
