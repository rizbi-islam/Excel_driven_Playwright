"""
app/__init__.py — Flask application factory.
Auto-migrates schema on startup (idempotent).
"""
from flask import Flask, render_template
from config import Config


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)

    # Auto-migrate on every startup — handles old v9 schema automatically
    try:
        from app.database.schema import auto_migrate
        auto_migrate()
    except Exception as e:
        print(f"  ⚠ Auto-migrate warning (run --migrate manually if this persists): {e}")

    @app.after_request
    def no_cache(resp):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"]        = "no-cache"
        resp.headers["Expires"]       = "0"
        return resp

    from app.routes.auth      import bp as auth_bp
    from app.routes.dashboard import bp as dash_bp
    from app.routes.tester    import bp as tester_bp
    from app.routes.generate  import bp as gen_bp
    from app.routes.runs      import bp as runs_bp
    from app.routes.library   import bp as lib_bp
    from app.routes.history   import bp as hist_bp
    from app.routes.envs      import bp as envs_bp
    from app.routes.apis      import bp as apis_bp
    from app.routes.users     import bp as users_bp
    from app.routes.access      import bp as access_bp
    from app.routes.collections import bp as col_bp

    for bp in (auth_bp, dash_bp, tester_bp, gen_bp, runs_bp,
               lib_bp, hist_bp, envs_bp, apis_bp, users_bp, access_bp, col_bp):
        app.register_blueprint(bp)

    @app.route("/api-tester")
    def api_tester():
        return render_template("api_tester.html")

    @app.route("/collections")
    def collections():
        return render_template("collections.html")

    return app
