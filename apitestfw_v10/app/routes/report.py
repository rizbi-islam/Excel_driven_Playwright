"""
app/routes/report.py — HTML Report viewer.

POST /api/report/collection → run collection → redirect to HTML report
GET  /report/<run_token>    → view stored HTML report
"""
import json
import hashlib
import time
from flask import Blueprint, request, jsonify, render_template, abort, session
from app.auth.decorators            import login_required, get_current_user
from app.database.models.collection import CollectionModel, CollectionRequestModel

bp = Blueprint("report", __name__)

# In-memory report store (keyed by token, expires after 1h)
# For production, store in DB or Redis. Fine for dev/testing use.
_reports: dict[str, dict] = {}


def _token(uid: int) -> str:
    return hashlib.sha256(f"{uid}-{time.time()}".encode()).hexdigest()[:24]


@bp.route("/api/report/collection/<int:cid>", methods=["POST"])
@login_required
def api_run_and_report(cid):
    """Run collection, store report, return token for HTML view."""
    user = get_current_user()
    d    = request.get_json(silent=True) or {}
    col  = CollectionModel.get(cid, user["id"])
    if not col: return jsonify(ok=False, error="Not found"), 404

    reqs = CollectionRequestModel.all_for_collection(cid, user["id"])
    req_ids = d.get("request_ids")
    if req_ids:
        reqs = [r for r in reqs if r["id"] in req_ids]
    if not reqs: return jsonify(ok=False, error="No requests"), 400

    from app.core.collection_runner import run_collection
    report = run_collection(dict(col), reqs)
    report["collection_name"] = col["name"]
    report["ran_at"]          = time.strftime("%Y-%m-%d %H:%M:%S")

    token = _token(user["id"])
    _reports[token] = {"report": report, "expires": time.time() + 3600}

    return jsonify(ok=True, token=token,
                   url=f"/report/{token}",
                   summary=report["summary"])


@bp.route("/report/<token>")
@login_required
def html_report(token):
    """Render the HTML report."""
    entry = _reports.get(token)
    if not entry or time.time() > entry["expires"]:
        abort(404)
    report = entry["report"]
    user   = get_current_user()
    return render_template("report.html", user=user, pg="history",
                           report=report,
                           report_json=json.dumps(report))


@bp.route("/report/view")
@login_required
def report_viewer():
    """Standalone page to paste/upload a JSON report and view as HTML."""
    user = get_current_user()
    return render_template("report_viewer.html", user=user, pg="history")
