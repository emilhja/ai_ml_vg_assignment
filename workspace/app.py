from auth.middleware import require_auth
from auth.session import load_session
from utils import render_response


def bar(user_id: str) -> str:
    session = load_session(user_id)
    return render_response("baz", session["user_id"])


@require_auth
def protected_dashboard(request):
    return render_response("dashboard", request.user_id)


if __name__ == "__main__":
    print(bar("demo-user"))
