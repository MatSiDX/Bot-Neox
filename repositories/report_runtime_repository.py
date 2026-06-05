import os

from repositories.balance_repository import DATA_DIR
from utils.json_store import mutate_json, read_json, write_json


REPORT_RUNTIME_FILE = os.path.join(DATA_DIR, "report_runtime.json")


class ReportRuntimeRepository:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(REPORT_RUNTIME_FILE):
            self.save(self.default_storage())

    def default_storage(self):
        return {
            "pending_reviews": {},
            "pending_balance_decisions": {},
        }

    def load(self):
        data = read_json(REPORT_RUNTIME_FILE, self.default_storage())
        if not isinstance(data, dict):
            return self.default_storage()

        data.setdefault("pending_reviews", {})
        data.setdefault("pending_balance_decisions", {})
        return data

    def save(self, data):
        write_json(REPORT_RUNTIME_FILE, data)

    def upsert_review(self, state):
        key = str(state["message_id"])

        def mutate(data):
            storage = self.load() if data is None else data
            storage.setdefault("pending_reviews", {})[key] = state
            storage.setdefault("pending_balance_decisions", storage.get("pending_balance_decisions", {}))
            return storage

        mutate_json(REPORT_RUNTIME_FILE, self.default_storage(), mutate)

    def remove_review(self, message_id):
        key = str(message_id)

        def mutate(data):
            storage = self.load() if data is None else data
            storage.setdefault("pending_reviews", {}).pop(key, None)
            storage.setdefault("pending_balance_decisions", storage.get("pending_balance_decisions", {}))
            return storage

        mutate_json(REPORT_RUNTIME_FILE, self.default_storage(), mutate)

    def get_reviews(self):
        return list(self.load().get("pending_reviews", {}).values())

    def upsert_balance_decision(self, state):
        key = str(state["message_id"])

        def mutate(data):
            storage = self.load() if data is None else data
            storage.setdefault("pending_balance_decisions", {})[key] = state
            storage.setdefault("pending_reviews", storage.get("pending_reviews", {}))
            return storage

        mutate_json(REPORT_RUNTIME_FILE, self.default_storage(), mutate)

    def remove_balance_decision(self, message_id):
        key = str(message_id)

        def mutate(data):
            storage = self.load() if data is None else data
            storage.setdefault("pending_balance_decisions", {}).pop(key, None)
            storage.setdefault("pending_reviews", storage.get("pending_reviews", {}))
            return storage

        mutate_json(REPORT_RUNTIME_FILE, self.default_storage(), mutate)

    def get_balance_decisions(self):
        return list(self.load().get("pending_balance_decisions", {}).values())
