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
import requests


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


def post_request_example():
    # Base URL
    url = "https://example.com/api/endpoint"  # Replace with your endpoint

    # Params (Query Parameters)
    params = {
        "key1": "value1",
        "key2": "value2"
    }

    # Auth (Authentication)
    auth = ("username", "password")  # Replace with your credentials

    # Headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer <your_token>"  # Replace with your token
    }

    # Body (JSON Payload)
    body = {
        "field1": "value1",
        "field2": "value2"
    }

    # Pre-request (Any setup before the request, e.g., generating tokens)
    # Example: Generate a dynamic token
    # token = generate_token()
    # headers["Authorization"] = f"Bearer {token}"

    try:
        # Sending the POST request
        response = requests.post(url, params=params, auth=auth, headers=headers, json=body)

        # Tests (Validating the response)
        if response.status_code == 200:
            print("Request successful!")
            print("Response:", response.json())
        else:
            print(f"Request failed with status code {response.status_code}")
            print("Response:", response.text)

    except requests.exceptions.RequestException as e:
        print("An error occurred:", e)


if __name__ == "__main__":
    main()
