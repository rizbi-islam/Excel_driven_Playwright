"""app/routes/apis.py — Registered APIs management."""
from flask import Blueprint, render_template, request, jsonify

from app.auth.decorators           import login_required, require_page, get_current_user
from app.database.models.api_model import ApiModel

bp = Blueprint("apis", __name__)


@bp.route("/apis")
@login_required
@require_page("apis")
def apis_page():
    user = get_current_user()
    return render_template("apis.html", user=user, pg="apis",
                           apis=ApiModel.all_for_user(user["id"]))


@bp.route("/api/apis/create", methods=["POST"])
@login_required
def api_create():
    user = get_current_user()
    d    = request.get_json(silent=True) or {}
    name = (d.get("name")     or "").strip()
    url  = (d.get("base_url") or "").strip()
    if not name or not url:
        return jsonify(ok=False, error="name and base_url are required"), 400
    aid = ApiModel.create(user["id"], name, url, d.get("description", ""))
    return jsonify(ok=True, id=aid)


@bp.route("/api/apis/<int:aid>/delete", methods=["POST"])
@login_required
def api_delete(aid):
    ApiModel.delete(aid, get_current_user()["id"])
    return jsonify(ok=True)
