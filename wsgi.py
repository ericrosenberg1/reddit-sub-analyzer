"""WSGI entry point for production deployment."""
from subsearch.web_app import app

# This is the application instance that gunicorn will use
if __name__ == "__main__":
    app.run()
