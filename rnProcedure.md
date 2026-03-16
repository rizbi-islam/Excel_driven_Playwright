# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure database — copy and fill in your MySQL credentials
cp .env.example .env
# Edit .env: set DB_HOST, DB_USER, DB_PASS, DB_NAME

# 3. First-time setup — creates DB, all tables, seeds admin user
python main.py --setup

# 4. Start the server
python main.py
# Open: http://127.0.0.1:5000
# Login: admin / admin123