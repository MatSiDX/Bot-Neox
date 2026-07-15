import json
import os
import tempfile
import unittest
from unittest.mock import patch

from repositories.dashboard_admin_security_repository import DashboardAdminSecurityRepository
from src.neox.core.repositories.config_repository import ConfigRepository
from src.neox.core.services.dashboard_admin_security_service import (
    ADMIN_SECURITY_CONFIG_SCOPE,
    CONFIG_ALLOWLIST_RECORD_KEY,
    CONFIG_PASSWORD_RECORD_KEY,
    DashboardAdminAccessError,
    DashboardAdminSecurityService,
    PasswordHasher,
)


@unittest.skipIf(PasswordHasher is None, "argon2-cffi no esta instalado en este entorno")
class DashboardAdminSecurityServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_file = os.path.join(self.temp_dir.name, "bot.sqlite3")
        self.config_file = os.path.join(self.temp_dir.name, "config.json")
        patches = [
            patch("repositories.database.DATA_DIR", self.temp_dir.name),
            patch("repositories.database.DATABASE_FILE", self.database_file),
            patch("src.neox.core.repositories.config_repository.DATA_DIR", self.temp_dir.name),
            patch("src.neox.core.repositories.config_repository.CONFIG_FILE", self.config_file),
        ]
        for item in patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(patches)])
        self.addCleanup(self.temp_dir.cleanup)

        self.config_repository = ConfigRepository()
        self.security_repository = DashboardAdminSecurityRepository()
        self.session_store = FakeSessionStore()

    def build_service(self, *, password_hash, developer_user_ids=("123",), max_attempts=5):
        return DashboardAdminSecurityService(
            config_repository=self.config_repository,
            security_repository=self.security_repository,
            session_store=self.session_store,
            configured_password_hash=password_hash,
            password_pepper="pepper-secreta",
            developer_user_ids=developer_user_ids,
            elevated_ttl_seconds=600,
            max_attempts=max_attempts,
            attempt_window_seconds=300,
            lockout_seconds=600,
        )

    def test_verify_password_elevates_session_and_rehashes_outdated_hash(self):
        weak_hasher = PasswordHasher(time_cost=2, memory_cost=1024, parallelism=2, hash_len=16, salt_len=16)
        original_hash = weak_hasher.hash("clave-secundariapepper-secreta")
        service = self.build_service(password_hash=original_hash)
        session = {"user": {"id": "123", "username": "Neox"}}

        service.synchronize_settings()
        status = service.verify_password(
            session=session,
            has_admin_permission=True,
            ip_address="127.0.0.1",
            password="clave-secundaria",
        )

        self.assertTrue(status["elevated"])
        self.assertTrue(self.session_store.get_elevated_session(session))
        stored_record = json.loads(
            self.config_repository.get_value(
                ADMIN_SECURITY_CONFIG_SCOPE,
                CONFIG_PASSWORD_RECORD_KEY,
                default="{}",
            )
        )
        self.assertNotEqual(stored_record["hash"], original_hash)

    def test_verify_password_locks_after_repeated_failures(self):
        service = self.build_service(
            password_hash=PasswordHasher().hash("clave-okpepper-secreta"),
            max_attempts=2,
        )
        session = {"user": {"id": "123", "username": "Neox"}}

        service.synchronize_settings()
        with self.assertRaises(DashboardAdminAccessError) as first_error:
            service.verify_password(
                session=session,
                has_admin_permission=True,
                ip_address="127.0.0.1",
                password="mal-1",
            )
        self.assertEqual(first_error.exception.status, 403)

        with self.assertRaises(DashboardAdminAccessError) as second_error:
            service.verify_password(
                session=session,
                has_admin_permission=True,
                ip_address="127.0.0.1",
                password="mal-2",
            )
        self.assertEqual(second_error.exception.status, 423)

        status = service.get_status(
            session=session,
            has_admin_permission=True,
            ip_address="127.0.0.1",
        )
        self.assertGreater(status["retryAfterSeconds"], 0)

    def test_synchronize_settings_audits_allowlist_changes_and_secret_rotation(self):
        first_hash = PasswordHasher().hash("clave-unopepper-secreta")
        second_hash = PasswordHasher().hash("clave-dospepper-secreta")

        first_service = self.build_service(
            password_hash=first_hash,
            developer_user_ids=("100", "200"),
        )
        first_service.synchronize_settings()

        second_service = self.build_service(
            password_hash=second_hash,
            developer_user_ids=("200", "300"),
        )
        second_service.synchronize_settings()

        allowlist_record = json.loads(
            self.config_repository.get_value(
                ADMIN_SECURITY_CONFIG_SCOPE,
                CONFIG_ALLOWLIST_RECORD_KEY,
                default="{}",
            )
        )
        self.assertEqual(allowlist_record["user_ids"], ["200", "300"])

        event_types = [event["event_type"] for event in self.security_repository.list_audit_events(limit=20)]
        self.assertIn("secret_rotated", event_types)
        self.assertIn("developer_allowlist_added", event_types)
        self.assertIn("developer_allowlist_removed", event_types)


class FakeSessionStore:
    def get_elevated_session(self, session):
        return session.get("admin_elevated_session")

    def set_elevated_session(self, session, *, user_id, ttl_seconds):
        session["admin_elevated_session"] = {
            "user_id": str(user_id or ""),
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2099-01-01T00:10:00Z" if ttl_seconds else "",
        }
        return dict(session["admin_elevated_session"])

    def clear_elevated_session(self, session):
        return session.pop("admin_elevated_session", None)


if __name__ == "__main__":
    unittest.main()
