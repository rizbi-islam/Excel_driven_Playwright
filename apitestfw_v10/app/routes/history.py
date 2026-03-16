"""app/routes/history.py — Run history and result viewer."""
from flask import Blueprint, render_template, abort

from app.auth.decorators      import login_required, require_page, get_current_user
from app.database.models.run  import (LoadMetricModel, ResultModel,
                                       RunModel, SecurityFindingModel)

bp = Blueprint("history", __name__)


@bp.route("/history")
@login_required
@require_page("history")
def history_page():
    user = get_current_user()
    runs = RunModel.all_for_user(user["id"])
    return render_template("history.html", user=user, pg="history", runs=runs)


@bp.route("/result/<int:rid>")
@login_required
def result_page(rid):
    user = get_current_user()
    run  = RunModel.get(rid, user["id"])
    if not run:
        abort(404)
    return render_template(
        "result.html",
        user     = user,
        pg       = "history",
        run      = run,
        results  = ResultModel.for_run(rid, user["id"]),
        metrics  = LoadMetricModel.for_run(rid, user["id"]),
        findings = SecurityFindingModel.for_run(rid, user["id"]),
    )
