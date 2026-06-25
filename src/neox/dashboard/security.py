import base64
import hashlib
import secrets
from http.cookies import SimpleCookie


def safe_dashboard_next(value):
    value = str(value or "").strip()
    if value.startswith("/dashboard") and not value.startswith("//"):
        return value
    return "/dashboard"


class DashboardCookieManager:
    def __init__(self, *, session_cookie_name, state_cookie_name, session_secret):
        self.session_cookie_name = session_cookie_name
        self.state_cookie_name = state_cookie_name
        self.session_secret = str(session_secret or "")

    def make_session_cookie(self, value, max_age=None):
        cookie = SimpleCookie()
        cookie[self.session_cookie_name] = value
        cookie[self.session_cookie_name]["path"] = "/"
        cookie[self.session_cookie_name]["samesite"] = "Lax"
        cookie[self.session_cookie_name]["httponly"] = True
        if max_age is not None:
            cookie[self.session_cookie_name]["max-age"] = str(int(max_age))
        return cookie.output(header="").strip()

    def make_state_cookie(self, value, max_age=300):
        cookie = SimpleCookie()
        cookie[self.state_cookie_name] = value
        cookie[self.state_cookie_name]["path"] = "/"
        cookie[self.state_cookie_name]["samesite"] = "Lax"
        cookie[self.state_cookie_name]["httponly"] = True
        cookie[self.state_cookie_name]["max-age"] = str(int(max_age))
        return cookie.output(header="").strip()

    def parse_cookie_header(self, header):
        cookie = SimpleCookie()
        if header:
            cookie.load(header)
        return {key: morsel.value for key, morsel in cookie.items()}

    def sign_session_id(self, session_id):
        digest = hashlib.sha256(f"{session_id}.{self.session_secret}".encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def encode_session_cookie(self, session_id):
        return f"{session_id}.{self.sign_session_id(session_id)}"

    def decode_session_cookie(self, value):
        if not value or "." not in value:
            return None

        session_id, signature = value.rsplit(".", 1)
        expected = self.sign_session_id(session_id)
        if not secrets.compare_digest(signature, expected):
            return None

        return session_id
