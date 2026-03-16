"""
app/routes/tester.py — API Tester.

403 FIX: require_page is ONLY on the page route, NOT on API endpoints.
The page guard is sufficient. Double-guarding caused 403 when page_access
rows were missing. login_required on API endpoints is enough.

Save-as-case is EXPLICIT only (user presses Add button). No auto-save.
"""
import json
from flask import Blueprint, render_template, request, jsonify, session
from app.auth.decorators             import login_required, require_page, get_current_user
from app.core.http_client            import HttpClient
from app.core.runner                 import expand_batch
from app.database.connection         import execute, query
from app.database.models.environment import EnvironmentModel
from app.database.models.test_case   import TestCaseModel
from app.database.models.api_model   import ApiModel

bp = Blueprint("tester", __name__)


@bp.route("/tester")
@login_required
@require_page("tester")
def tester_page():
    user    = get_current_user()
    envs    = EnvironmentModel.all_for_user(user["id"])
    apis    = ApiModel.all_for_user(user["id"])
    history = query(
        "SELECT id,method,url,response_status,response_ms,ran_at "
        "FROM tester_history WHERE owner_id=%s ORDER BY ran_at DESC LIMIT 50",
        (user["id"],)
    )
    return render_template("tester.html", user=user, pg="tester",
                           envs=envs, apis=apis, history=history)


# ── Send (login_required ONLY — no require_page on API endpoints) ─

@bp.route("/api/send-request", methods=["POST"])
@login_required
def api_send_request():
    d         = request.get_json(silent=True) or {}
    method    = (d.get("method") or "GET").upper()
    url       = (d.get("url") or "").strip()
    timeout   = min(int(d.get("timeout") or 30), 120)

    if not url:
        return jsonify(ok=False, error="URL is required", status=0,
                       status_text="Error", response_ms=0, size=0, body="",
                       resp_headers={}, redirects=0)

    headers   = _build_headers(d)
    _apply_auth(d, headers)
    params    = _build_params(d)
    body_type = d.get("body_type", "none")
    body      = d.get("body")

    result = HttpClient.send(
        method=method, url=url, headers=headers, params=params,
        body_type=body_type, body=body, timeout=timeout,
        follow_redirects=bool(d.get("follow_redirects", True)),
    )
    _persist_history(session.get("user_id"), method, url, headers, params,
                     body_type, d.get("body"), result)
    return jsonify(**result)


# ── Batch / parameterized ─────────────────────────────────────────

@bp.route("/api/batch-send", methods=["POST"])
@login_required
def api_batch_send():
    d       = request.get_json(silent=True) or {}
    method  = (d.get("method") or "GET").upper()
    url     = (d.get("url") or "").strip()
    timeout = min(int(d.get("timeout") or 30), 60)
    if not url:
        return jsonify(ok=False, error="URL is required"), 400

    headers = _build_headers(d)
    _apply_auth(d, headers)
    params  = _build_params(d)
    body    = d.get("body")
    combos  = expand_batch(params, body)
    if len(combos) > 50:
        return jsonify(ok=False, error="Batch max is 50 items"), 400

    uid = session.get("user_id")
    results = []
    for p, b in combos:
        btype = "json" if b is not None else "none"
        r = HttpClient.send(method=method, url=url, headers=headers, params=p,
                            body_type=btype, body=b, timeout=timeout,
                            follow_redirects=bool(d.get("follow_redirects", True)))
        r["batch_params"] = p
        r["batch_body"]   = b
        results.append(r)
        _persist_history(uid, method, url, headers, p, btype, b, r)
    return jsonify(ok=True, batch=True, results=results, count=len(results))


# ── Explicit save-as-case (Add button only, never auto) ──────────

@bp.route("/api/tester/save-as-case", methods=["POST"])
@login_required
def api_save_as_case():
    user = get_current_user()
    d    = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    url  = (d.get("url")  or "").strip()
    if not name: return jsonify(ok=False, error="Test case name is required"), 400
    if not url:  return jsonify(ok=False, error="URL is required"), 400

    case = {
        "name":            name,
        "method":          (d.get("method") or "GET").upper(),
        "endpoint":        url,
        "headers":         d.get("headers") or {},
        "body":            d.get("body"),
        "params":          d.get("params") or {},
        "expected_status": int(d.get("expected_status") or 200),
        "auth_type":       d.get("auth_type", "none"),
        "auth_token":      d.get("auth_token", ""),
        "assertions":      d.get("assertions") or [],
        "tags":            d.get("tags") or [],
        "description":     d.get("description", ""),
        "sheet_type":      d.get("sheet_type", "regression"),
        "test_type":       d.get("test_type", "regression"),
        "api_id":          d.get("api_id"),
        "is_active":       1,
    }
    cid = TestCaseModel.save(user["id"], case)
    return jsonify(ok=True, id=cid)


# ── History ───────────────────────────────────────────────────────

@bp.route("/api/tester/history")
@login_required
def api_history_list():
    uid  = session.get("user_id")
    rows = query(
        "SELECT id,method,url,response_status,response_ms,ran_at "
        "FROM tester_history WHERE owner_id=%s ORDER BY ran_at DESC LIMIT 50",
        (uid,)
    )
    return jsonify(ok=True, history=[dict(r) for r in rows])


@bp.route("/api/tester/history/<int:hid>")
@login_required
def api_history_detail(hid):
    uid  = session.get("user_id")
    rows = query("SELECT * FROM tester_history WHERE id=%s AND owner_id=%s", (hid, uid))
    if not rows: return jsonify(ok=False, error="Not found"), 404
    r = dict(rows[0])
    if isinstance(r.get("request_data"), str):
        try:    r["request_data"] = json.loads(r["request_data"])
        except: pass
    return jsonify(ok=True, item=r)


@bp.route("/api/tester/history/<int:hid>/delete", methods=["POST"])
@login_required
def api_history_delete(hid):
    execute("DELETE FROM tester_history WHERE id=%s AND owner_id=%s",
            (hid, session.get("user_id")))
    return jsonify(ok=True)


@bp.route("/api/tester/history/clear", methods=["POST"])
@login_required
def api_history_clear():
    execute("DELETE FROM tester_history WHERE owner_id=%s", (session.get("user_id"),))
    return jsonify(ok=True)


# ── Helpers ───────────────────────────────────────────────────────

def _build_headers(d):
    raw = d.get("headers") or {}
    if isinstance(raw, dict):  return {k: v for k, v in raw.items() if k and v is not None}
    if isinstance(raw, list):  return {r["key"]: r["value"] for r in raw if r.get("key") and r.get("value") is not None}
    return {}

def _build_params(d):
    raw = d.get("params") or {}
    if isinstance(raw, dict):  return {k: v for k, v in raw.items() if k}
    if isinstance(raw, list):  return {r["key"]: r["value"] for r in raw if r.get("key")}
    return {}

def _apply_auth(d, headers):
    at = d.get("auth_type", "none"); av = d.get("auth_value", "")
    if   at == "bearer" and av: headers["Authorization"]                      = f"Bearer {av}"
    elif at == "basic"  and av: headers["Authorization"]                      = f"Basic {av}"
    elif at == "apikey" and av: headers[d.get("auth_key_name", "X-API-Key")] = av

def _persist_history(uid, method, url, headers, params, body_type, body, result):
    if not uid: return
    try:
        execute(
            "INSERT INTO tester_history(owner_id,method,url,request_data,"
            "response_status,response_ms,response_size) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (uid, method, url,
             json.dumps({"headers": headers, "params": params,
                         "body_type": body_type, "body": body}),
             result["status"], result["response_ms"], result["size"])
        )
    except Exception:
        pass
