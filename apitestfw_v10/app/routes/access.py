"""
app/routes/access.py — Per-USER page access management (admin only).

UI: Users × Pages grid. Each cell is a checkbox.
Admin can toggle any user/page combination independently of role.
Bulk save: saves entire grid in one call.
Reset button: resets a user back to their role defaults.
"""
from flask import Blueprint, render_template, request, jsonify

from app.auth.decorators         import login_required, admin_only, get_current_user
from app.database.models.access  import AccessModel, ALL_PAGES
from app.database.models.user    import UserModel

bp = Blueprint("access", __name__)


@bp.route("/access")
@login_required
@admin_only
def access_page():
    user      = get_current_user()
    # Show all non-admin users (admin always has full access)
    all_users = [u for u in UserModel.all() if u["role"] != "admin"]
    matrix    = AccessModel.get_all_matrix()   # {user_id: {page: bool}}
    return render_template(
        "access.html",
        user      = user,
        pg        = "access",
        all_users = all_users,
        all_pages = ALL_PAGES,
        matrix    = matrix,
    )


@bp.route("/api/access/matrix")
@login_required
@admin_only
def api_get_matrix():
    all_users = [u for u in UserModel.all() if u["role"] != "admin"]

    def safe(u):
        row = dict(u)
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
        return row

    return jsonify(
        ok     = True,
        matrix = AccessModel.get_all_matrix(),
        users  = [safe(u) for u in all_users],
    )


@bp.route("/api/access/save-all", methods=["POST"])
@login_required
@admin_only
def api_save_all():
    """
    Save entire matrix in one call.
    Body: {matrix: {"1": {"dashboard": true, "tester": false, ...}, "2": {...}}}
    """
    d      = request.get_json(silent=True) or {}
    matrix = d.get("matrix") or {}
    total  = 0
    errors = []

    for uid_str, pages in matrix.items():
        try:
            count = AccessModel.save_user_matrix(int(uid_str), pages)
            total += count
        except Exception as exc:
            errors.append(f"user {uid_str}: {exc}")

    return jsonify(ok=not errors, total_updated=total, errors=errors)


@bp.route("/api/access/user/<int:uid>/save", methods=["POST"])
@login_required
@admin_only
def api_save_user(uid):
    """Save one user's page matrix. Body: {pages: {page: bool}}"""
    d     = request.get_json(silent=True) or {}
    pages = d.get("pages")
    if not isinstance(pages, dict):
        return jsonify(ok=False, error="Expected {pages: {...}}"), 400
    count = AccessModel.save_user_matrix(uid, pages)
    return jsonify(ok=True, updated=count)


@bp.route("/api/access/user/<int:uid>/reset", methods=["POST"])
@login_required
@admin_only
def api_reset_user(uid):
    """Reset this user's page access to their role's defaults."""
    user = UserModel.find_by_id(uid)
    if not user:
        return jsonify(ok=False, error="User not found"), 404
    AccessModel.reset_to_role(uid, user["role"])
    return jsonify(ok=True, role=user["role"])
