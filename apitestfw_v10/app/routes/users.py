"""app/routes/users.py — User management (admin only)."""
from flask import Blueprint, render_template, request, jsonify

from app.auth.decorators         import login_required, admin_only, get_current_user
from app.auth.security           import hash_password
from app.database.models.access  import AccessModel
from app.database.models.user    import UserModel

bp = Blueprint("users", __name__)


@bp.route("/users")
@login_required
@admin_only
def users_page():
    user      = get_current_user()
    all_users = UserModel.all()
    return render_template("users.html", user=user, pg="users", all_users=all_users)


@bp.route("/api/users/create", methods=["POST"])
@login_required
@admin_only
def api_create_user():
    d        = request.get_json(silent=True) or {}
    username = (d.get("username") or "").strip()
    email    = (d.get("email")    or "").strip()
    password = (d.get("password") or "").strip()
    role     =  d.get("role", "tester")

    if not username or not email or not password:
        return jsonify(ok=False, error="username, email, password are required"), 400
    if role not in ("admin", "tester", "viewer"):
        return jsonify(ok=False, error="role must be admin, tester or viewer"), 400
    if len(password) < 6:
        return jsonify(ok=False, error="Password must be at least 6 characters"), 400

    try:
        uid = UserModel.create(username, email, hash_password(password), role)
        # Seed page access from role defaults
        AccessModel.seed_for_user(uid, role)
        return jsonify(ok=True, id=uid)
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 409


@bp.route("/api/users/<int:uid>/toggle", methods=["POST"])
@login_required
@admin_only
def api_toggle_user(uid):
    UserModel.toggle_active(uid)
    user = UserModel.find_by_id(uid)
    return jsonify(ok=True, is_active=bool(user["is_active"]) if user else False)


@bp.route("/api/users/<int:uid>/role", methods=["POST"])
@login_required
@admin_only
def api_set_role(uid):
    d    = request.get_json(silent=True) or {}
    role = d.get("role")
    if role not in ("admin", "tester", "viewer"):
        return jsonify(ok=False, error="Invalid role"), 400
    UserModel.update_role(uid, role)
    # Reset page access to new role defaults
    AccessModel.reset_to_role(uid, role)
    return jsonify(ok=True)


@bp.route("/api/users/<int:uid>/password", methods=["POST"])
@login_required
@admin_only
def api_set_password(uid):
    d   = request.get_json(silent=True) or {}
    pwd = (d.get("password") or "").strip()
    if len(pwd) < 6:
        return jsonify(ok=False, error="Password must be at least 6 characters"), 400
    UserModel.update_password(uid, hash_password(pwd))
    return jsonify(ok=True)
