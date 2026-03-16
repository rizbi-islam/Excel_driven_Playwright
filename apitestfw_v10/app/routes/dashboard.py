"""app/routes/dashboard.py — Home page."""
from flask import Blueprint, render_template

from app.auth.decorators      import login_required, get_current_user
from app.database.models.run  import StatsModel, RunModel

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    user        = get_current_user()
    stats       = StatsModel.for_user(user["id"])
    recent_runs = RunModel.all_for_user(user["id"], limit=5)
    return render_template("dashboard.html", user=user, pg="dashboard",
                           stats=stats, recent_runs=recent_runs)
