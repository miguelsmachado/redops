"""
WSGI entry point.
Run directly with `python wsgi.py` for local development,
or via gunicorn (`gunicorn wsgi:app`) for production/Docker.
"""
import os
from src.entrypoints.flask_app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)
