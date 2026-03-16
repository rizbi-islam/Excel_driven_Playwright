"""
app/routes/collections.py — Full Postman-parity collection API.
"""
import json
from flask import Blueprint, request, jsonify, session, render_template
from app.auth.decorators            import login_required, get_current_user
from app.database.models.collection import CollectionModel, CollectionRequestModel

bp = Blueprint("collections", __name__)


# ── Page ─────────────────────────────────────────────────────────

@bp.route("/collections")
@login_required
def collections_page():
    user = get_current_user()
    cols = CollectionModel.all_for_user(user["id"])
    return render_template("collections.html", user=user, pg="collections", collections=cols)


# ── Collection CRUD ───────────────────────────────────────────────

@bp.route("/api/collections", methods=["GET"])
@login_required
def api_list():
    user = get_current_user()
    cols = CollectionModel.all_for_user(user["id"])
    return jsonify(ok=True, collections=[_safe(c) for c in cols])


@bp.route("/api/collections", methods=["POST"])
@login_required
def api_create():
    user = get_current_user()
    d    = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name: return jsonify(ok=False, error="Name required"), 400
    cid = CollectionModel.create(user["id"], d)
    return jsonify(ok=True, id=cid)


@bp.route("/api/collections/<int:cid>", methods=["GET"])
@login_required
def api_get(cid):
    user = get_current_user()
    col  = CollectionModel.get(cid, user["id"])
    if not col: return jsonify(ok=False, error="Not found"), 404
    reqs = CollectionRequestModel.all_for_collection(cid, user["id"])
    return jsonify(ok=True, collection=_safe(col),
                   requests=[_safe_req(r) for r in reqs])


@bp.route("/api/collections/<int:cid>", methods=["POST"])
@login_required
def api_update(cid):
    user = get_current_user()
    d    = request.get_json(silent=True) or {}
    CollectionModel.update(cid, user["id"], d)
    return jsonify(ok=True)


@bp.route("/api/collections/<int:cid>/delete", methods=["POST"])
@login_required
def api_delete(cid):
    CollectionModel.delete(cid, get_current_user()["id"])
    return jsonify(ok=True)


@bp.route("/api/collections/<int:cid>/duplicate", methods=["POST"])
@login_required
def api_duplicate(cid):
    user   = get_current_user()
    new_id = CollectionModel.duplicate(cid, user["id"])
    return jsonify(ok=True, id=new_id)


# ── Requests CRUD ─────────────────────────────────────────────────

@bp.route("/api/collections/<int:cid>/requests", methods=["POST"])
@login_required
def api_add_request(cid):
    user = get_current_user()
    col  = CollectionModel.get(cid, user["id"])
    if not col: return jsonify(ok=False, error="Collection not found"), 404
    d = request.get_json(silent=True) or {}
    if not d.get("url"): return jsonify(ok=False, error="url required"), 400
    rid = CollectionRequestModel.save(user["id"], cid, d)
    return jsonify(ok=True, id=rid)


@bp.route("/api/collections/requests/<int:rid>", methods=["GET"])
@login_required
def api_get_request(rid):
    user = get_current_user()
    r    = CollectionRequestModel.get(rid, user["id"])
    if not r: return jsonify(ok=False, error="Not found"), 404
    return jsonify(ok=True, request=_safe_req(r))


@bp.route("/api/collections/requests/<int:rid>/update", methods=["POST"])
@login_required
def api_update_request(rid):
    user = get_current_user()
    d    = request.get_json(silent=True) or {}
    CollectionRequestModel.update(rid, user["id"], d)
    return jsonify(ok=True)


@bp.route("/api/collections/requests/<int:rid>/delete", methods=["POST"])
@login_required
def api_delete_request(rid):
    CollectionRequestModel.delete(rid, get_current_user()["id"])
    return jsonify(ok=True)


@bp.route("/api/collections/<int:cid>/reorder", methods=["POST"])
@login_required
def api_reorder(cid):
    user       = get_current_user()
    d          = request.get_json(silent=True) or {}
    ordered_ids = d.get("ids", [])
    CollectionRequestModel.reorder(cid, user["id"], ordered_ids)
    return jsonify(ok=True)


# ── Runner ────────────────────────────────────────────────────────

@bp.route("/api/collections/<int:cid>/run", methods=["POST"])
@login_required
def api_run_collection(cid):
    """
    Run all (or selected) requests in a collection, return full report.
    Body: { request_ids?: [int], delay_ms?: int }
    """
    user = get_current_user()
    d    = request.get_json(silent=True) or {}
    col  = CollectionModel.get(cid, user["id"])
    if not col: return jsonify(ok=False, error="Collection not found"), 404

    reqs = CollectionRequestModel.all_for_collection(cid, user["id"])

    # Filter to specific IDs if provided
    req_ids = d.get("request_ids")
    if req_ids:
        reqs = [r for r in reqs if r["id"] in req_ids]

    if not reqs:
        return jsonify(ok=False, error="No requests to run"), 400

    from app.core.collection_runner import run_collection
    report = run_collection(dict(col), reqs)
    return jsonify(ok=True, **report)


# ── Export ────────────────────────────────────────────────────────

@bp.route("/api/collections/<int:cid>/export", methods=["GET"])
@login_required
def api_export(cid):
    """Export collection as JSON (Postman-compatible subset)."""
    user = get_current_user()
    col  = CollectionModel.get(cid, user["id"])
    if not col: return jsonify(ok=False, error="Not found"), 404
    reqs = CollectionRequestModel.all_for_collection(cid, user["id"])

    export = {
        "info": {
            "name":        col["name"],
            "description": col.get("description", ""),
            "schema":      "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": _export_auth(col),
        "variable": [
            {"key": v["key"], "value": v["value"]}
            for v in (col.get("variables") or [])
            if v.get("key")
        ],
        "event": _export_events(col),
        "item": [
            {
                "name":    r["name"],
                "request": {
                    "method":  r["method"],
                    "url":     {"raw": r["url"]},
                    "header":  [{"key": k, "value": v} for k, v in (r.get("headers") or {}).items()],
                    "body":    _export_body(r),
                    "auth":    _export_auth(r) if r.get("auth_type") not in ("inherit", "none", None) else None,
                    "description": r.get("description", ""),
                },
                "event": _export_events(r),
            }
            for r in reqs
        ],
    }
    return jsonify(export)


# ── Helpers ───────────────────────────────────────────────────────

def _safe(row):
    if row is None: return None
    r = dict(row)
    for k, v in r.items():
        if hasattr(v, "isoformat"): r[k] = v.isoformat()
    return r

def _safe_req(row):
    if row is None: return None
    r = dict(row)
    for k in ("headers", "body", "params"):
        if isinstance(r.get(k), str):
            try:    r[k] = json.loads(r[k])
            except: pass
    for k, v in r.items():
        if hasattr(v, "isoformat"): r[k] = v.isoformat()
    return r

def _export_auth(obj):
    at = obj.get("auth_type", "none")
    tok = obj.get("auth_token", "")
    if   at == "bearer": return {"type":"bearer","bearer":[{"key":"token","value":tok}]}
    elif at == "basic":  return {"type":"basic", "basic": [{"key":"password","value":tok}]}
    elif at == "apikey": return {"type":"apikey","apikey":[{"key":"value","value":tok}]}
    return {"type":"noauth"}

def _export_body(r):
    bt   = r.get("body_type","none")
    body = r.get("body")
    if bt == "none" or body is None: return {"mode":"none"}
    if bt == "json":
        raw = json.dumps(body) if not isinstance(body, str) else body
        return {"mode":"raw","raw":raw,"options":{"raw":{"language":"json"}}}
    if bt == "form":
        pairs = body.items() if isinstance(body, dict) else []
        return {"mode":"urlencoded","urlencoded":[{"key":k,"value":v} for k,v in pairs]}
    if bt == "multipart":
        pairs = body.items() if isinstance(body, dict) else []
        return {"mode":"formdata","formdata":[{"key":k,"value":v,"type":"text"} for k,v in pairs]}
    return {"mode":"raw","raw":str(body)}

def _export_events(obj):
    evts = []
    if obj.get("pre_request_script"):
        evts.append({"listen":"prerequest","script":{"exec":obj["pre_request_script"].splitlines()}})
    if obj.get("tests_script"):
        evts.append({"listen":"test","script":{"exec":obj["tests_script"].splitlines()}})
    return evts
