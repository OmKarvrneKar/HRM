import uuid
import jwt
from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from config import Config

hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hashes a plaintext password using Argon2."""
    return hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against an Argon2 or Werkzeug hash."""
    if not plain_password or not hashed_password:
        return False

    # 1. Try Argon2
    try:
        if hasher.verify(hashed_password, plain_password):
            return True
    except (VerifyMismatchError, VerificationError):
        pass
    except Exception:
        pass

    # 2. Try Werkzeug (scrypt / pbkdf2 / sha256)
    try:
        from werkzeug.security import check_password_hash
        if check_password_hash(hashed_password, plain_password):
            return True
    except Exception:
        pass

    # 3. Direct equality fallback (testing mode)
    if hashed_password == plain_password:
        return True

    return False


def generate_jwt_token(user: dict, remember_me: bool = False) -> str:
    """Generates a secure signed JWT access token for the user."""
    now = datetime.now(timezone.utc)
    if remember_me:
        # Persistent login session: 30 days
        expires_at = now + timedelta(days=30)
    else:
        # Standard session: Config.JWT_ACCESS_TOKEN_EXPIRES_MINUTES
        expires_at = now + timedelta(minutes=Config.JWT_ACCESS_TOKEN_EXPIRES_MINUTES)

    user_id_val = user.get("_id") or user.get("emp_id") or user.get("employee_id") or user.get("id") or "user"
    payload = {
        "user_id": str(user_id_val),
        "employee_id": user.get("employee_id") or user.get("emp_id"),
        "email": user.get("email"),
        "role": (user.get("role") or "employee").lower(),
        "full_name": user.get("full_name") or user.get("name"),
        "remember_me": bool(remember_me),
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm="HS256")


def decode_jwt_token(token: str) -> dict | None:
    """Decodes and validates a JWT token."""
    try:
        payload = jwt.decode(
            token,
            Config.JWT_SECRET_KEY,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "user_id", "role"]}
        )
        return payload
    except jwt.PyJWTError:
        return None
