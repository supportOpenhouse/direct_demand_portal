from datetime import timedelta

import jwt as pyjwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import settings
from app.core.utils import utcnow


def verify_google_token(credential: str) -> str:
    """Verify a Google ID token and return the email it asserts.

    Raises ValueError (from google-auth) on any invalid / expired / wrong-audience token.
    """
    idinfo = id_token.verify_oauth2_token(
        credential, google_requests.Request(), settings.GOOGLE_CLIENT_ID
    )
    email = idinfo.get("email")
    if not email:
        raise ValueError("Google token carries no email")
    return email


def create_jwt(user) -> str:
    now = utcnow()
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "team_id": str(user.team_id) if user.team_id else None,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.JWT_EXPIRY_HOURS)).timestamp()),
    }
    return pyjwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_jwt(token: str) -> dict:
    return pyjwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
