"""
app/routes/generate.py — Auto-generate test cases from endpoint analysis.

Flow:
  1. User enters base URL + endpoint list.
  2. POST /api/generate/analyze → probes each endpoint → returns analysis.
  3. User reviews the table (can edit names, expected status, etc.)
  4. POST /api/generate/save → stores cases to my_cases DB.
  5. User goes to library → toggles active/skip per row → runs.
  6. Also: POST /api/generate/excel → download Excel (offline review).
"""
import base64
import json

from flask import Blueprint, render_template, request, jsonify

from app.auth.decorators             import login_required, require_page, get_current_user
from app.core.http_client            import HttpClient
from app.core.excel_generator        import ExcelGenerator
from app.database.models.environment import EnvironmentModel
from app.database.models.test_case   import TestCaseModel

bp = Blueprint("generate", __name__)


@bp.route("/generate")
@login_required
@require_page("generate")
def generate_page():
    user = get_current_user()
    envs = EnvironmentModel.all_for_user(user["id"])
    return render_template("generate.html", user=user, pg="generate", envs=envs)


# ── Analyze endpoints ─────────────────────────────────────────────

@bp.route("/api/generate/analyze", methods=["POST"])
@login_required
def api_analyze():
    d         = request.get_json(silent=True) or {}
    base_url  = (d.get("base_url") or "").strip().rstrip("/")
    endpoints = d.get("endpoints") or []
    auth_type = d.get("auth_type", "none")
    auth_tok  = d.get("auth_token", "")

    if not base_url:
        return jsonify(ok=False, error="base_url is required"), 400
    if not endpoints:
        return jsonify(ok=False, error="At least one endpoint is required"), 400
    if len(endpoints) > 30:
        return jsonify(ok=False, error="Max 30 endpoints per request"), 400

    global_hdrs: dict = {}
    if   auth_type == "bearer" and auth_tok: global_hdrs["Authorization"] = f"Bearer {auth_tok}"
    elif auth_type == "basic"  and auth_tok: global_hdrs["Authorization"] = f"Basic {auth_tok}"
    elif auth_type == "apikey" and auth_tok: global_hdrs["X-API-Key"]     = auth_tok

    analyses = []
    for ep in endpoints:
        path      = (ep.get("path") or "").strip().lstrip("/")
        method    = (ep.get("method") or "GET").upper()
        url       = f"{base_url}/{path}" if path else base_url
        probe_m   = method if ep.get("probe_with_method") else "GET"
        body      = ep.get("body") if probe_m != "GET" else None
        body_type = "json" if body is not None else "none"

        result = HttpClient.send(
            method=probe_m, url=url, headers=dict(global_hdrs),
            body_type=body_type, body=body, timeout=15,
        )

        body_sample = None
        if result["body"]:
            try:
                parsed = json.loads(result["body"])
                if isinstance(parsed, list) and parsed:
                    body_sample = parsed[0] if isinstance(parsed[0], dict) else {"item": parsed[0]}
                elif isinstance(parsed, dict):
                    body_sample = dict(list(parsed.items())[:8])
            except Exception:
                pass

        analyses.append({
            "path":        ep.get("path", "/"+path),
            "method":      method,
            "name":        ep.get("name", ""),
            "status":      result["status"],
            "body_sample": body_sample,
            "latency_ms":  result["response_ms"],
            "error":       result.get("error"),
            "ok":          result["ok"],
            "auth_type":   auth_type,
            "auth_token":  auth_tok,
        })

    return jsonify(ok=True, analyses=analyses, base_url=base_url)


# ── Save generated cases to DB ────────────────────────────────────

@bp.route("/api/generate/save", methods=["POST"])
@login_required
def api_generate_save():
    """
    Save the reviewed/edited generated cases directly to my_cases table.
    User presses 'Save to Library' after reviewing analysis results.
    """
    user      = get_current_user()
    d         = request.get_json(silent=True) or {}
    base_url  = (d.get("base_url") or "").strip()
    cases     = d.get("cases") or []
    api_id    = d.get("api_id")

    if not cases:
        return jsonify(ok=False, error="No cases provided"), 400

    saved = 0
    for case in cases:
        if not case.get("endpoint"):
            continue
        case_data = {
            "name":            case.get("name") or case.get("endpoint"),
            "method":          (case.get("method") or "GET").upper(),
            "endpoint":        case.get("endpoint"),
            "headers":         case.get("headers") or {},
            "body":            case.get("body"),
            "params":          case.get("params") or {},
            "expected_status": int(case.get("expected_status") or 200),
            "auth_type":       case.get("auth_type", "none"),
            "auth_token":      case.get("auth_token", ""),
            "assertions":      case.get("assertions") or [],
            "tags":            case.get("tags") or [],
            "description":     case.get("description", ""),
            "sheet_type":      case.get("sheet_type", "regression"),
            "test_type":       case.get("test_type", "regression"),
            "api_id":          int(api_id) if api_id else None,
            "is_active":       1 if case.get("is_active", True) else 0,
        }
        try:
            TestCaseModel.save(user["id"], case_data)
            saved += 1
        except Exception:
            pass

    return jsonify(ok=True, saved=saved)


# ── Download Excel ────────────────────────────────────────────────

@bp.route("/api/generate/excel", methods=["POST"])
@login_required
def api_generate_excel():
    d         = request.get_json(silent=True) or {}
    base_url  = (d.get("base_url") or "").strip()
    endpoints = d.get("endpoints") or []
    analyses  = d.get("analyses")  or []

    if not base_url or not endpoints:
        return jsonify(ok=False, error="base_url and endpoints required"), 400

    while len(analyses) < len(endpoints):
        analyses.append({"status": 200, "body_sample": None, "error": None})

    try:
        raw_bytes = ExcelGenerator.generate(base_url, endpoints, analyses[:len(endpoints)])
        return jsonify(ok=True,
                       data=base64.b64encode(raw_bytes).decode(),
                       filename="api_test_suite.xlsx",
                       size=len(raw_bytes))
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 500
