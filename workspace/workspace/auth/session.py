SESSION_SECRET = "fixture-secret"


def issue_token(user_id: str) -> str:
    return f"token::{user_id}::{SESSION_SECRET}"


def validate_token(token: str) -> bool:
    parts = token.split("::")
    return len(parts) == 3 and parts[0] == "token" and parts[2] == SESSION_SECRET


def load_session(user_id: str) -> dict[str, str]:
    token = issue_token(user_id)
    if not validate_token(token):
        raise ValueError("invalid session token")
    return {"user_id": user_id, "token": token}
