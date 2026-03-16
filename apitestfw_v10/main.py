"""
main.py — Entry point. No business logic here.

Usage:
    python main.py --setup       # First time: create DB + tables + seed admin
    python main.py --migrate     # Safe migrations on existing data
    python main.py               # Run the server (default port 5000)
    python main.py --port 8080 --debug
"""
import sys
import argparse
from app import create_app
from app.database.schema import init_db, migrate_db


def main():
    parser = argparse.ArgumentParser(description="API Test Framework v10")
    parser.add_argument("--setup",   action="store_true", help="Initialize DB and seed defaults")
    parser.add_argument("--migrate", action="store_true", help="Run safe DB migrations")
    parser.add_argument("--port",    type=int, default=5000, help="Port (default: 5000)")
    parser.add_argument("--debug",   action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    if args.setup:
        print("→ Setting up database...")
        init_db()
        print("✅ Setup complete.")
        print("   Default login: admin / admin123")
        print("   Start server:  python main.py")
        sys.exit(0)

    if args.migrate:
        print("→ Running migrations...")
        migrate_db()
        print("✅ Migrations complete.")
        sys.exit(0)

    app = create_app()
    print(f"✅ API Test Framework v10 running on http://127.0.0.1:{args.port}")
    print(f"   Debug: {args.debug}")
    app.run(host="0.0.0.0", port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
