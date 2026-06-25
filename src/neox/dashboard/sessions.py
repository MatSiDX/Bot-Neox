import secrets
import time

from src.neox.dashboard.security import safe_dashboard_next


class DashboardSessionStore:
    def __init__(
        self,
        *,
        sessions,
        sessions_lock,
        oauth_states,
        oauth_states_lock,
        sessions_file,
        read_json,
        write_json,
        cookie_manager,
        session_cookie_name,
        session_ttl_seconds,
        remember_session_ttl_seconds,
    ):
        self.sessions = sessions
        self.sessions_lock = sessions_lock
        self.oauth_states = oauth_states
        self.oauth_states_lock = oauth_states_lock
        self.sessions_file = sessions_file
        self.read_json = read_json
        self.write_json = write_json
        self.cookie_manager = cookie_manager
        self.session_cookie_name = session_cookie_name
        self.session_ttl_seconds = session_ttl_seconds
        self.remember_session_ttl_seconds = remember_session_ttl_seconds

    def remember_oauth_state(self, state, remember_device=False, next_path="/dashboard"):
        with self.oauth_states_lock:
            self.oauth_states[state] = {
                "expires_at": time.time() + 300,
                "remember_device": bool(remember_device),
                "next_path": safe_dashboard_next(next_path),
            }

    def consume_oauth_state(self, state):
        if not state:
            return False

        now = time.time()
        with self.oauth_states_lock:
            expired = [
                key
                for key, payload in self.oauth_states.items()
                if payload.get("expires_at", 0) < now
            ]
            for key in expired:
                self.oauth_states.pop(key, None)

            payload = self.oauth_states.pop(state, None)
            if not payload or payload.get("expires_at", 0) < now:
                return None

            return payload

    def load_persisted_sessions(self):
        sessions = self.read_json(self.sessions_file, {})
        if not isinstance(sessions, dict):
            return {}

        now = time.time()
        return {
            session_id: session
            for session_id, session in sessions.items()
            if isinstance(session, dict) and session.get("expires_at", 0) >= now
        }

    def save_persisted_sessions(self):
        self.write_json(self.sessions_file, self.sessions)

    def create_session(self, user, admin_guilds, guilds=None, remember_device=False):
        session_id = secrets.token_urlsafe(32)
        ttl = self.remember_session_ttl_seconds if remember_device else self.session_ttl_seconds
        with self.sessions_lock:
            self.sessions[session_id] = {
                "user": user,
                "admin_guilds": admin_guilds,
                "guilds": guilds or admin_guilds,
                "expires_at": time.time() + ttl,
                "remember_device": bool(remember_device),
                "csrf_token": secrets.token_urlsafe(24),
            }
            self.save_persisted_sessions()
        return session_id

    def get_session_from_request(self, handler):
        cookies = self.cookie_manager.parse_cookie_header(handler.headers.get("Cookie", ""))
        session_id = self.cookie_manager.decode_session_cookie(cookies.get(self.session_cookie_name, ""))
        if not session_id:
            return None

        with self.sessions_lock:
            session = self.sessions.get(session_id)
            if not session:
                return None
            if session.get("expires_at", 0) < time.time():
                self.sessions.pop(session_id, None)
                self.save_persisted_sessions()
                return None
            if not session.get("csrf_token"):
                session["csrf_token"] = secrets.token_urlsafe(24)
                self.save_persisted_sessions()
            return session

    def clear_session_from_request(self, handler):
        cookies = self.cookie_manager.parse_cookie_header(handler.headers.get("Cookie", ""))
        session_id = self.cookie_manager.decode_session_cookie(cookies.get(self.session_cookie_name, ""))
        if session_id:
            with self.sessions_lock:
                self.sessions.pop(session_id, None)
                self.save_persisted_sessions()
