# passenger_wsgi.py — cPanel Passenger / WSGI entry point for the Legal RAG Flask app.
#
# The app is now a native Flask (WSGI) application — no subprocess proxy needed.
# Passenger imports this file once per worker and calls `application(environ, start_response)`.

import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Load .env before importing the app so all os.getenv() calls inside flask_app
# and the backend modules pick up the values at import time.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(APP_DIR, ".env"))
except ImportError:
    pass  # rely on environment being set in cPanel app settings

from flask_app import app as application  # noqa: E402  (Passenger entry point)

if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", 5000))
    application.run(host="0.0.0.0", port=port, debug=False)
