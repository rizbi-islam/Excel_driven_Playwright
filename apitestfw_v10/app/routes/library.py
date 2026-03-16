"""
app/routes/library.py — Test case library.

New features:
- is_active toggle per case (run/skip column)
- Import Excel → store ALL rows to DB
- Run only active cases for a given type
"""
import json
import threading

from flask import Blueprint, render_template, request, jsonify, current_app

from app.auth.decorators           import login_required, require_page, get_current_user
from app.core.excel_parser         import ExcelParser
from app.core.runner               import run_cases
from app.database.models.api_model import ApiModel
from app.database.models.run       import RunModel, ResultModel
from app.database.models.test_case import TestCaseModel

bp = Blueprint("library", __name__)


@bp.route("/library")
@login_required
@require_page("library")
def library_page():
    user  = get_current_user()
    cases = TestCaseModel.all_for_user(user["id"])
    apis  = ApiModel.all_for_user(user["id"])
    return render_template("library.html", user=user, pg="library",
                           cases=cases, apis=apis)


# ── List / get ────────────────────────────────────────────────────

@bp.route("/api/cases")
@login_required
def api_list_cases():
    user       = get_current_user()
    api_id     = request.args.get("api_id")
    sheet_type = request.args.get("sheet_type") or request.args.get("test_type")
    active_only= request.args.get("active_only") == "1"

    cases = TestCaseModel.all_for_user(
        user["id"],
        api_id     = int(api_id) if api_id else None,
        sheet_type = sheet_type,
    )
    if active_only:
        cases = [c for c in cases if c.get("is_active", 1)]

    def safe(c):
        row = dict(c)
        for k, v in row.items():
            if hasattr(v, "isoformat"): row[k] = v.isoformat()
        return row

    return jsonify(ok=True, cases=[safe(c) for c in cases])


@bp.route("/api/cases/<int:cid>")
@login_required
def api_get_case(cid):
    user = get_current_user()
    c    = TestCaseModel.get(cid, user["id"])
    if not c: return jsonify(ok=False, error="Not found"), 404
    return jsonify(ok=True, case=dict(c))


# ── Toggle active/skip ────────────────────────────────────────────

@bp.route("/api/cases/<int:cid>/toggle", methods=["POST"])
@login_required
def api_toggle_case(cid):
    user     = get_current_user()
    new_state = TestCaseModel.toggle_active(cid, user["id"])
    return jsonify(ok=True, is_active=new_state)


# ── Save single case ──────────────────────────────────────────────

@bp.route("/api/cases/save", methods=["POST"])
@login_required
def api_save_case():
    user = get_current_user()
    d    = request.get_json(silent=True) or {}
    if not d.get("name") or not d.get("endpoint"):
        return jsonify(ok=False, error="name and endpoint are required"), 400
    cid = TestCaseModel.save(user["id"], d)
    return jsonify(ok=True, id=cid)


# ── Import Excel → store all rows to DB ──────────────────────────

@bp.route("/api/cases/import-excel", methods=["POST"])
@login_required
def api_import_excel():
    """
    Upload an Excel file → parse → store ALL rows to my_cases DB table.
    User can then toggle rows on/off before running.
    """
    user      = get_current_user()
    f         = request.files.get("file")
    test_type = (request.form.get("test_type") or "regression").strip()
    api_id    = request.form.get("api_id") or None

    if not f:
        return jsonify(ok=False, error="No file uploaded"), 400

    try:
        cases, detected_type, warnings = ExcelParser.parse_file(f.read(), test_type)
    except Exception as exc:
        return jsonify(ok=False, error=f"Parse error: {exc}"), 400

    if not cases:
        return jsonify(ok=False, error="No valid cases found in file"), 400

    saved = 0
    for case in cases:
        case["api_id"]    = int(api_id) if api_id else None
        case["is_active"] = 1
        try:
            TestCaseModel.save(user["id"], case)
            saved += 1
        except Exception:
            pass

    return jsonify(ok=True, saved=saved, total=len(cases),
                   warnings=warnings, test_type=detected_type)


# ── Run active cases from library ─────────────────────────────────

@bp.route("/api/cases/run", methods=["POST"])
@login_required
def api_run_cases():
    """
    Run all active cases for a given type (or specific case IDs).
    Runs in background thread, returns run_id immediately.
    """
    user      = get_current_user()
    d         = request.get_json(silent=True) or {}
    base_url  = (d.get("base_url") or "").strip()
    test_type =  d.get("test_type", "regression")
    label     =  d.get("label") or f"{test_type} run"
    api_id    =  d.get("api_id")
    case_ids  =  d.get("case_ids")   # optional: run only these IDs

    if not base_url:
        return jsonify(ok=False, error="base_url is required"), 400

    all_cases = TestCaseModel.all_for_user(
        user["id"],
        api_id     = int(api_id) if api_id else None,
        sheet_type = test_type,
    )

    # Filter to active only (or specific IDs if provided)
    if case_ids:
        cases = [c for c in all_cases if c["id"] in case_ids]
    else:
        cases = [c for c in all_cases if c.get("is_active", 1)]

    if not cases:
        return jsonify(ok=False, error="No active cases found for this type"), 400

    cases = [_row_to_dict(c) for c in cases]

    extra = {
        "concurrency":  int(d.get("concurrency") or 10),
        "duration_sec": int(d.get("duration_sec") or 30),
        "start_users":  int(d.get("start_users") or 1),
        "peak_users":   int(d.get("peak_users") or 50),
        "ramp_sec":     int(d.get("ramp_sec") or 60),
    }

    run_id = RunModel.create(user["id"], api_id, label, base_url, test_type,
                             source="library", concurrency=extra["concurrency"])

    def _bg():
        try:
            summary = run_cases(cases=cases, base_url=base_url, test_type=test_type,
                                run_id=run_id, owner_id=user["id"], **extra)
            RunModel.finish(run_id, summary["total"], summary["passed"],
                            summary["failed"], summary["duration"])
        except Exception:
            RunModel.error(run_id)

    threading.Thread(target=_bg, daemon=True).start()

    return jsonify(ok=True, run_id=run_id, total_cases=len(cases), status="running")


# ── Delete ────────────────────────────────────────────────────────

@bp.route("/api/cases/<int:cid>/delete", methods=["POST"])
@login_required
def api_delete_case(cid):
    TestCaseModel.delete(cid, get_current_user()["id"])
    return jsonify(ok=True)


# ── Helper ────────────────────────────────────────────────────────

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
