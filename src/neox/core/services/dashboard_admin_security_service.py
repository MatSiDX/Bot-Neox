from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

from repositories.dashboard_admin_security_repository import DashboardAdminSecurityRepository
from src.neox.config.settings import (
    DASHBOARD_ADMIN_ATTEMPT_WINDOW_SECONDS,
    DASHBOARD_ADMIN_DEVELOPER_IDS,
    DASHBOARD_ADMIN_ELEVATED_TTL_SECONDS,
    DASHBOARD_ADMIN_LOCKOUT_SECONDS,
    DASHBOARD_ADMIN_MAX_ATTEMPTS,
    DASHBOARD_ADMIN_PASSWORD_HASH,
    DASHBOARD_ADMIN_PASSWORD_PEPPER,
)
from src.neox.core.repositories.config_repository import ConfigRepository

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
except ImportError:  # pragma: no cover - depende del entorno local
    PasswordHasher = None

    class VerifyMismatchError(Exception):
        pass

    class VerificationError(Exception):
        pass

    class InvalidHashError(Exception):
        pass


ADMIN_SECURITY_CONFIG_SCOPE = "__dashboard_admin__"
CONFIG_PASSWORD_RECORD_KEY = "password_record"
CONFIG_ALLOWLIST_RECORD_KEY = "allowlist_record"


class DashboardAdminAccessError(RuntimeError):
    def __init__(self, message, *, status=403):
        super().__init__(message)
        self.status = int(status)


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _to_iso(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    timestamp = float(value)
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _seconds_until(value):
    parsed = _parse_iso(value)
    if not parsed:
        return 0
    return max(0, int((parsed - _utc_now()).total_seconds()))


def _json_loads(value):
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        loaded = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


class DashboardAdminSecurityService:
    def __init__(
        self,
        *,
        config_repository=None,
        security_repository=None,
        session_store=None,
        configured_password_hash=DASHBOARD_ADMIN_PASSWORD_HASH,
        password_pepper=DASHBOARD_ADMIN_PASSWORD_PEPPER,
        developer_user_ids=DASHBOARD_ADMIN_DEVELOPER_IDS,
        elevated_ttl_seconds=DASHBOARD_ADMIN_ELEVATED_TTL_SECONDS,
        max_attempts=DASHBOARD_ADMIN_MAX_ATTEMPTS,
        attempt_window_seconds=DASHBOARD_ADMIN_ATTEMPT_WINDOW_SECONDS,
        lockout_seconds=DASHBOARD_ADMIN_LOCKOUT_SECONDS,
    ):
        self.config_repository = config_repository or ConfigRepository()
        self.security_repository = security_repository or DashboardAdminSecurityRepository()
        self.session_store = session_store
        self.configured_password_hash = str(configured_password_hash or "").strip()
        self.password_pepper = str(password_pepper or "")
        self.developer_user_ids = self._normalize_user_ids(developer_user_ids)
        self.elevated_ttl_seconds = max(600, min(900, int(elevated_ttl_seconds or 900)))
        self.max_attempts = max(1, int(max_attempts or 5))
        self.attempt_window_seconds = max(60, int(attempt_window_seconds or 900))
        self.lockout_seconds = max(60, int(lockout_seconds or 900))
        self._settings_synced = False
        self._password_hasher = None

    @staticmethod
    def argon2_available():
        return PasswordHasher is not None

    def synchronize_settings(self):
        if self._settings_synced:
            return

        stored_password_record = self._read_password_record()
        stored_allowlist = set(self._read_allowlist_record().get("user_ids", []))

        if self.configured_password_hash:
            incoming_fingerprint = self._hash_fingerprint(self.configured_password_hash)
            stored_fingerprint = self._hash_fingerprint(stored_password_record.get("hash"))
            if stored_password_record.get("hash") != self.configured_password_hash:
                self._write_password_record({
                    "version": 1,
                    "scheme": "argon2id",
                    "hash": self.configured_password_hash,
                    "fingerprint": incoming_fingerprint,
                    "updated_at": _to_iso(_utc_now()),
                })
                if stored_fingerprint:
                    self._append_audit(
                        "secret_rotated",
                        actor_name="system",
                        details={
                            "previous_fingerprint": stored_fingerprint,
                            "current_fingerprint": incoming_fingerprint,
                        },
                    )

        if self.developer_user_ids:
            incoming_allowlist = set(self.developer_user_ids)
            if incoming_allowlist != stored_allowlist:
                self._write_allowlist_record({
                    "version": 1,
                    "user_ids": sorted(incoming_allowlist),
                    "updated_at": _to_iso(_utc_now()),
                })
                for added_user_id in sorted(incoming_allowlist - stored_allowlist):
                    self._append_audit(
                        "developer_allowlist_added",
                        actor_name="system",
                        details={"developer_user_id": added_user_id},
                    )
                for removed_user_id in sorted(stored_allowlist - incoming_allowlist):
                    self._append_audit(
                        "developer_allowlist_removed",
                        actor_name="system",
                        details={"developer_user_id": removed_user_id},
                    )

        self._settings_synced = True

    def get_status(self, *, session, has_admin_permission, ip_address):
        self.synchronize_settings()
        expired = self._clear_expired_elevation(session=session, ip_address=ip_address)
        allowlisted = self._is_allowlisted(session)
        lock_state = self._lock_state(session=session, ip_address=ip_address)
        elevated = self._session_is_elevated(session)
        status = {
            "configReady": self._config_ready(),
            "hasAdminPermission": bool(has_admin_permission),
            "allowlisted": allowlisted,
            "elevated": elevated,
            "expiresAt": "",
            "expiresInSeconds": 0,
            "lockedUntil": lock_state.get("locked_until", ""),
            "retryAfterSeconds": lock_state.get("retry_after_seconds", 0),
            "remainingAttempts": max(0, self.max_attempts - lock_state.get("user_failures", 0)),
            "expired": expired,
            "message": "",
        }
        payload = self._current_elevation(session)
        if elevated and payload:
            status["expiresAt"] = str(payload.get("expires_at") or "")
            status["expiresInSeconds"] = _seconds_until(payload.get("expires_at"))

        if not status["configReady"]:
            status["message"] = (
                "El refuerzo de seguridad del panel administrativo aun no esta configurado."
            )
        elif not status["hasAdminPermission"]:
            status["message"] = "Tu sesion no tiene permisos vigentes para abrir este panel."
        elif not status["allowlisted"]:
            status["message"] = "Tu usuario no esta autorizado para elevar acceso administrativo."
        elif status["retryAfterSeconds"] > 0:
            status["message"] = (
                "La clave secundaria esta bloqueada temporalmente por demasiados intentos fallidos."
            )
        elif status["elevated"]:
            status["message"] = "Acceso administrativo elevado activo."
        else:
            status["message"] = "Ingresa la clave secundaria para desbloquear el panel."
        return status

    def verify_password(self, *, session, has_admin_permission, ip_address, password):
        self.synchronize_settings()
        status = self.get_status(
            session=session,
            has_admin_permission=has_admin_permission,
            ip_address=ip_address,
        )
        if not status["configReady"]:
            raise DashboardAdminAccessError(status["message"], status=503)
        if not status["hasAdminPermission"]:
            raise DashboardAdminAccessError(status["message"], status=403)
        if not status["allowlisted"]:
            self._append_audit(
                "challenge_denied_not_allowlisted",
                actor_user_id=self._session_user_id(session),
                actor_name=self._session_actor_name(session),
                ip_address=ip_address,
            )
            raise DashboardAdminAccessError(status["message"], status=403)
        if status["retryAfterSeconds"] > 0:
            self._append_audit(
                "challenge_denied_locked",
                actor_user_id=self._session_user_id(session),
                actor_name=self._session_actor_name(session),
                ip_address=ip_address,
                details={"locked_until": status["lockedUntil"]},
            )
            raise DashboardAdminAccessError(status["message"], status=423)

        password = str(password or "")
        if not password:
            raise DashboardAdminAccessError("Debes ingresar la clave secundaria.", status=400)

        record = self._read_password_record()
        password_hash = str(record.get("hash") or "")
        if not password_hash:
            raise DashboardAdminAccessError(
                "El panel administrativo seguro no esta configurado.",
                status=503,
            )

        try:
            verified = self._password_hasher_instance().verify(
                password_hash,
                self._peppered_password(password),
            )
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            verified = False

        if not verified:
            lock_state = self._record_failure(session=session, ip_address=ip_address)
            self._append_audit(
                "challenge_failed",
                actor_user_id=self._session_user_id(session),
                actor_name=self._session_actor_name(session),
                ip_address=ip_address,
                details={
                    "locked_until": lock_state.get("locked_until", ""),
                    "remaining_attempts": max(0, self.max_attempts - lock_state.get("user_failures", 0)),
                },
            )
            if lock_state.get("retry_after_seconds", 0) > 0:
                raise DashboardAdminAccessError(
                    "La clave secundaria quedo bloqueada temporalmente tras demasiados intentos.",
                    status=423,
                )
            raise DashboardAdminAccessError("La clave secundaria es incorrecta.", status=403)

        if self._password_hasher_instance().check_needs_rehash(password_hash):
            refreshed_hash = self._password_hasher_instance().hash(self._peppered_password(password))
            self._write_password_record({
                "version": 1,
                "scheme": "argon2id",
                "hash": refreshed_hash,
                "fingerprint": self._hash_fingerprint(refreshed_hash),
                "updated_at": _to_iso(_utc_now()),
            })

        self._clear_failures(session=session, ip_address=ip_address)
        if self.session_store is not None:
            self.session_store.set_elevated_session(
                session,
                user_id=self._session_user_id(session),
                ttl_seconds=self.elevated_ttl_seconds,
            )
        self._append_audit(
            "challenge_succeeded",
            actor_user_id=self._session_user_id(session),
            actor_name=self._session_actor_name(session),
            ip_address=ip_address,
            details={"expires_in_seconds": self.elevated_ttl_seconds},
        )
        return self.get_status(
            session=session,
            has_admin_permission=has_admin_permission,
            ip_address=ip_address,
        )

    def ensure_elevated_access(self, *, session, has_admin_permission, ip_address):
        status = self.get_status(
            session=session,
            has_admin_permission=has_admin_permission,
            ip_address=ip_address,
        )
        if not status["configReady"]:
            raise DashboardAdminAccessError(status["message"], status=503)
        if not status["hasAdminPermission"] or not status["allowlisted"]:
            raise DashboardAdminAccessError(
                "No tienes acceso administrativo a este panel.",
                status=403,
            )
        if not status["elevated"]:
            if status["retryAfterSeconds"] > 0:
                raise DashboardAdminAccessError(status["message"], status=423)
            raise DashboardAdminAccessError(
                "Debes validar la clave secundaria antes de usar el panel administrativo.",
                status=403,
            )
        return status

    def logout_elevated(self, *, session, ip_address, reason="logout"):
        payload = self._current_elevation(session)
        if not payload:
            return False
        if self.session_store is not None:
            self.session_store.clear_elevated_session(session)
        self._append_audit(
            "elevated_session_logout" if reason == "logout" else "elevated_session_revoked",
            actor_user_id=self._session_user_id(session),
            actor_name=self._session_actor_name(session),
            ip_address=ip_address,
            details={"reason": reason},
        )
        return True

    def _config_ready(self):
        if not self.argon2_available():
            return False
        if not self.password_pepper:
            return False
        if not self._read_password_record().get("hash"):
            return False
        return bool(self._read_allowlist_record().get("user_ids"))

    def _current_elevation(self, session):
        if self.session_store is None:
            return None
        payload = self.session_store.get_elevated_session(session)
        return payload if isinstance(payload, dict) else None

    def _session_is_elevated(self, session):
        payload = self._current_elevation(session)
        if not payload:
            return False
        if str(payload.get("user_id") or "") != self._session_user_id(session):
            return False
        return _seconds_until(payload.get("expires_at")) > 0

    def _clear_expired_elevation(self, *, session, ip_address):
        payload = self._current_elevation(session)
        if not payload:
            return False
        if _seconds_until(payload.get("expires_at")) > 0:
            return False
        if self.session_store is not None:
            self.session_store.clear_elevated_session(session)
        self._append_audit(
            "elevated_session_expired",
            actor_user_id=self._session_user_id(session),
            actor_name=self._session_actor_name(session),
            ip_address=ip_address,
        )
        return True

    def _lock_state(self, *, session, ip_address):
        user_attempt = self._normalized_attempt("user", self._session_user_id(session))
        ip_attempt = self._normalized_attempt("ip", ip_address)
        candidates = [item for item in (user_attempt, ip_attempt) if item]
        locked_candidates = [item for item in candidates if item.get("retry_after_seconds", 0) > 0]
        strongest = max(locked_candidates, key=lambda item: item.get("retry_after_seconds", 0), default=None)
        return {
            "locked_until": strongest.get("locked_until", "") if strongest else "",
            "retry_after_seconds": strongest.get("retry_after_seconds", 0) if strongest else 0,
            "user_failures": user_attempt.get("failures", 0) if user_attempt else 0,
            "ip_failures": ip_attempt.get("failures", 0) if ip_attempt else 0,
        }

    def _normalized_attempt(self, subject_type, subject_key):
        subject_key = str(subject_key or "").strip()
        if not subject_key:
            return None
        attempt = self.security_repository.get_attempt(subject_type, subject_key)
        if not attempt:
            return None

        last_failure = _parse_iso(attempt.get("last_failure_at"))
        locked_until = attempt.get("locked_until", "")
        retry_after_seconds = _seconds_until(locked_until)
        if retry_after_seconds <= 0 and last_failure is not None:
            age_seconds = max(0, int((_utc_now() - last_failure).total_seconds()))
            if age_seconds >= self.attempt_window_seconds:
                self.security_repository.clear_attempt(subject_type, subject_key)
                return None

        return {
            **attempt,
            "retry_after_seconds": retry_after_seconds,
        }

    def _record_failure(self, *, session, ip_address):
        attempts = []
        for subject_type, subject_key in (
            ("user", self._session_user_id(session)),
            ("ip", ip_address),
        ):
            subject_key = str(subject_key or "").strip()
            if not subject_key:
                continue
            normalized = self._normalized_attempt(subject_type, subject_key) or {}
            failures = int(normalized.get("failures", 0))
            first_failure_at = normalized.get("first_failure_at", "")
            last_failure = _parse_iso(normalized.get("last_failure_at"))
            if not first_failure_at or last_failure is None:
                failures = 0
                first_failure_at = ""
            elif (_utc_now() - last_failure).total_seconds() >= self.attempt_window_seconds:
                failures = 0
                first_failure_at = ""

            failures += 1
            now_iso = _to_iso(_utc_now())
            if not first_failure_at:
                first_failure_at = now_iso
            locked_until = ""
            if failures >= self.max_attempts:
                locked_until = _to_iso(time.time() + self.lockout_seconds)
            attempts.append(
                self.security_repository.save_attempt(
                    subject_type=subject_type,
                    subject_key=subject_key,
                    failures=failures,
                    first_failure_at=first_failure_at,
                    last_failure_at=now_iso,
                    locked_until=locked_until,
                )
            )

        user_attempt = next((item for item in attempts if item["subject_type"] == "user"), None)
        ip_attempt = next((item for item in attempts if item["subject_type"] == "ip"), None)
        return {
            "locked_until": max(
                (item.get("locked_until", "") for item in attempts),
                default="",
            ),
            "retry_after_seconds": max(
                (_seconds_until(item.get("locked_until")) for item in attempts),
                default=0,
            ),
            "user_failures": int(user_attempt.get("failures", 0)) if user_attempt else 0,
            "ip_failures": int(ip_attempt.get("failures", 0)) if ip_attempt else 0,
        }

    def _clear_failures(self, *, session, ip_address):
        for subject_type, subject_key in (
            ("user", self._session_user_id(session)),
            ("ip", ip_address),
        ):
            if str(subject_key or "").strip():
                self.security_repository.clear_attempt(subject_type, subject_key)

    def _append_audit(self, event_type, *, actor_user_id="", actor_name="", ip_address="", details=None):
        self.security_repository.append_audit_event(
            event_type=event_type,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            ip_address=ip_address,
            details=details,
        )

    def _read_password_record(self):
        return _json_loads(
            self.config_repository.get_value(
                ADMIN_SECURITY_CONFIG_SCOPE,
                CONFIG_PASSWORD_RECORD_KEY,
                default="",
            )
        )

    def _write_password_record(self, record):
        self.config_repository.set_value(
            ADMIN_SECURITY_CONFIG_SCOPE,
            CONFIG_PASSWORD_RECORD_KEY,
            json.dumps(record, ensure_ascii=False, sort_keys=True),
        )

    def _read_allowlist_record(self):
        record = _json_loads(
            self.config_repository.get_value(
                ADMIN_SECURITY_CONFIG_SCOPE,
                CONFIG_ALLOWLIST_RECORD_KEY,
                default="",
            )
        )
        record["user_ids"] = self._normalize_user_ids(record.get("user_ids"))
        return record

    def _write_allowlist_record(self, record):
        clean_record = {
            **(record or {}),
            "user_ids": self._normalize_user_ids((record or {}).get("user_ids")),
        }
        self.config_repository.set_value(
            ADMIN_SECURITY_CONFIG_SCOPE,
            CONFIG_ALLOWLIST_RECORD_KEY,
            json.dumps(clean_record, ensure_ascii=False, sort_keys=True),
        )

    def _is_allowlisted(self, session):
        user_id = self._session_user_id(session)
        if not user_id:
            return False
        return user_id in set(self._read_allowlist_record().get("user_ids", []))

    def _password_hasher_instance(self):
        if self._password_hasher is None:
            if PasswordHasher is None:
                raise DashboardAdminAccessError(
                    "Falta instalar argon2-cffi para proteger el panel administrativo.",
                    status=503,
                )
            self._password_hasher = PasswordHasher(
                time_cost=3,
                memory_cost=65536,
                parallelism=4,
                hash_len=32,
                salt_len=16,
            )
        return self._password_hasher

    def _peppered_password(self, password):
        return f"{str(password or '')}{self.password_pepper}"

    def _session_user_id(self, session):
        user = session.get("user", {}) if isinstance(session, dict) else {}
        return str(user.get("id") or "")

    def _session_actor_name(self, session):
        user = session.get("user", {}) if isinstance(session, dict) else {}
        return str(user.get("global_name") or user.get("username") or "Dashboard")

    def _hash_fingerprint(self, value):
        clean = str(value or "").strip()
        if not clean:
            return ""
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]

    def _normalize_user_ids(self, values):
        normalized = []
        for value in values or []:
            clean = str(value or "").strip()
            if clean and clean not in normalized:
                normalized.append(clean)
        return tuple(normalized)
