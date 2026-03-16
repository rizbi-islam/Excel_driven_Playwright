"""
app/auth/decorators.py — Route decorators.

KEY FIX: Access control is now PER-USER (not per-role).
- Admin always passes without a DB hit.
- All other users are checked against page_access table keyed on (user_id, page).
- When a user is created, their page_access rows are seeded from role defaults.
- Admin can then customize any user's access independently of their role.
"""
from functools import wraps
from flask import session, redirect, url_for, abort
from app.database.models.user   import UserModel
from app.database.models.access import AccessModel


def get_current_user() -> dict | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return UserModel.find_by_id(uid)


def login_required(f):
    """Redirect to /login if no active session."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


def admin_only(f):
    """Abort 403 if user is not admin role."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or user.get("role") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def require_page(page_key: str):
    """
    Per-user page access check.
    Admin always passes.
    Others: checked against page_access table (user_id, page) → allowed.
    Usage:
        @bp.route("/tester")
        @login_required
        @require_page("tester")
        def tester_page(): ...
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return redirect(url_for("auth.login"))
            # Admin always passes — no DB hit needed
            if user.get("role") == "admin":
                return f(*args, **kwargs)
            # Per-user check
            if not AccessModel.user_can(user["id"], page_key):
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator
