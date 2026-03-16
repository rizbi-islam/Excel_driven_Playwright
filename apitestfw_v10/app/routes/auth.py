"""app/routes/auth.py — Login / Logout."""
from flask import Blueprint, render_template, request, session, redirect, url_for
from app.auth.security        import verify_password
from app.database.models.user import UserModel

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password =  request.form.get("password") or ""
        user     = UserModel.find_by_username(username)

        if user and bool(user["is_active"]) and verify_password(password, user["password"]):
            session["user_id"]  = user["id"]
            session["username"] = user["username"]
            session["role"]     = user["role"]
            UserModel.update_last_login(user["id"])

            # Ensure this user has page_access rows (idempotent, fast)
            try:
                from app.database.models.access import AccessModel
                AccessModel.seed_for_user(user["id"], user["role"])
            except Exception:
                pass  # Never block login over this

            return redirect(url_for("dashboard.index"))

        error = "Invalid username or password."

    return render_template("login.html", error=error)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
