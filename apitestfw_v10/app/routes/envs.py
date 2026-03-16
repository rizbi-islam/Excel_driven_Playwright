"""app/routes/envs.py — Environment management."""
from flask import Blueprint, render_template, request, jsonify

from app.auth.decorators             import login_required, require_page, get_current_user
from app.database.models.environment import EnvironmentModel

bp = Blueprint("envs", __name__)


@bp.route("/envs")
@login_required
@require_page("envs")
def envs_page():
    user = get_current_user()
    envs = EnvironmentModel.all_for_user(user["id"])
    return render_template("envs.html", user=user, pg="envs", envs=envs)


@bp.route("/api/envs")
@login_required
def api_list_envs():
    user = get_current_user()
    def safe(e):
        row = dict(e)
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
        return row
    return jsonify(ok=True, envs=[safe(e) for e in EnvironmentModel.all_for_user(user["id"])])


@bp.route("/api/envs/create", methods=["POST"])
@login_required
def api_create_env():
    user = get_current_user()
    d    = request.get_json(silent=True) or {}
    if not d.get("name") or not d.get("base_url"):
        return jsonify(ok=False, error="name and base_url are required"), 400
    eid = EnvironmentModel.create(user["id"], d)
    return jsonify(ok=True, id=eid)


@bp.route("/api/envs/<int:eid>/set-default", methods=["POST"])
@login_required
def api_set_default(eid):
    EnvironmentModel.set_default(eid, get_current_user()["id"])
    return jsonify(ok=True)


@bp.route("/api/envs/<int:eid>/delete", methods=["POST"])
@login_required
def api_delete_env(eid):
    EnvironmentModel.delete(eid, get_current_user()["id"])
    return jsonify(ok=True)
