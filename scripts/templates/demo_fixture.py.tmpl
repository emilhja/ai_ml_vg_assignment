"""Generated deterministic fixture repository."""

from __future__ import annotations

from pathlib import Path


APP = """from auth.middleware import require_auth
from auth.session import load_session
from utils import render_response


def foo(user_id: str) -> str:
    session = load_session(user_id)
    return render_response("foo", session["user_id"])


@require_auth
def protected_dashboard(request):
    return render_response("dashboard", request.user_id)


if __name__ == "__main__":
    print(foo("demo-user"))
"""

SESSION = """SESSION_SECRET = "fixture-secret"


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
"""

MIDDLEWARE = """from functools import wraps

from .session import validate_token


class AuthError(RuntimeError):
    pass


def require_auth(handler):
    @wraps(handler)
    def wrapper(request, *args, **kwargs):
        token = getattr(request, "token", "")
        if not validate_token(token):
            raise AuthError("authentication required")
        return handler(request, *args, **kwargs)

    return wrapper
"""

UTILS = """def render_response(name: str, user_id: str) -> str:
    return f"{name}: {user_id}"
"""


def sample_log() -> str:
    lines = []
    for i in range(4600):
        lines.append(f"2026-05-10T12:{i % 60:02d}:00Z INFO request_id=req-{i:05d} route=/health status=200 latency_ms={20 + (i % 17)}")
    return "\n".join(lines) + "\n"


def write_fixture(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "auth").mkdir(exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "app.py").write_text(APP, encoding="utf-8", newline="\n")
    (root / "auth" / "__init__.py").write_text("", encoding="utf-8", newline="\n")
    (root / "auth" / "session.py").write_text(SESSION, encoding="utf-8", newline="\n")
    (root / "auth" / "middleware.py").write_text(MIDDLEWARE, encoding="utf-8", newline="\n")
    (root / "utils.py").write_text(UTILS, encoding="utf-8", newline="\n")
    (root / "README.md").write_text("# Demo Repo\n\nSmall auth-heavy fixture for VG Agent demos.\n", encoding="utf-8", newline="\n")
    (root / "data" / "sample.log").write_text(sample_log(), encoding="utf-8", newline="\n")
