import os

from app import create_app


app = create_app()

# Vercel/serverless-friendly overrides: keep your existing Config logic,
# but allow environment variables to supply production credentials.
_db_uri = os.environ.get("SQLALCHEMY_DATABASE_URI") or os.environ.get("DATABASE_URL")
if _db_uri:
    app.config["SQLALCHEMY_DATABASE_URI"] = _db_uri

_secret = os.environ.get("SECRET_KEY")
if _secret:
    app.config["SECRET_KEY"] = _secret

