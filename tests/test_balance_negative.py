import os
import shutil
import sqlite3
import unittest
import uuid
from contextlib import contextmanager
from unittest import mock

import repositories.balance_repository as balance_module
import repositories.database as database_module
from repositories.balance_repository import BalanceRepository


class BalanceNegativeTests(unittest.TestCase):
    def setUp(self):
        temp_root = os.path.join(os.getcwd(), ".tmp")
        os.makedirs(temp_root, exist_ok=True)
        self.data_dir = os.path.join(temp_root, f"balance-negative-{uuid.uuid4().hex}")
        os.makedirs(self.data_dir, exist_ok=True)
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row

        @contextmanager
        def test_connection():
            try:
                yield self.connection
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

        self.patches = [
            mock.patch.object(balance_module, "DATA_DIR", self.data_dir),
            mock.patch.object(balance_module, "DATA_FILE", os.path.join(self.data_dir, "balances.json")),
            mock.patch.object(database_module, "DATA_DIR", self.data_dir),
            mock.patch.object(database_module, "DATABASE_FILE", os.path.join(self.data_dir, "bot.sqlite3")),
            mock.patch.object(database_module, "get_connection", test_connection),
        ]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        self.connection.close()
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_remove_can_leave_silver_negative(self):
        repository = BalanceRepository()

        new_balance = repository.modify_balance("guild-1", "user-1", 500, "silver", add=False)

        self.assertEqual(new_balance, -500)
        self.assertEqual(repository.get_balance("guild-1", "user-1"), (0, -500))

    def test_signed_internal_adjustment_can_leave_silver_negative(self):
        repository = BalanceRepository()

        repository.modify_balance("guild-1", "user-1", 200, "silver", add=True)
        new_balance = repository.modify_balance("guild-1", "user-1", "-350", "silver", add=True)

        self.assertEqual(new_balance, -150)
        self.assertEqual(repository.get_balance("guild-1", "user-1"), (0, -150))

    def test_negative_totals_are_ranked_after_positive_totals(self):
        repository = BalanceRepository()
        repository.modify_balance("guild-1", "1001", 100, "silver", add=True)
        repository.modify_balance("guild-1", "1002", 50, "silver", add=False)

        self.assertEqual(
            repository.get_ranking("guild-1"),
            [(1001, 100), (1002, -50)],
        )

    def test_invalid_amounts_are_rejected(self):
        repository = BalanceRepository()

        for amount in (None, True, "", "  ", "10.5", "NaN", "inf", object(), 0):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    repository.modify_balance("guild-1", "user-1", amount, "silver", add=True)


if __name__ == "__main__":
    unittest.main()
