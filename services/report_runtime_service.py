from repositories.report_runtime_repository import ReportRuntimeRepository


class ReportRuntimeService:
    def __init__(self):
        self.repo = ReportRuntimeRepository()

    def save_review(self, state):
        self.repo.upsert_review(state)

    def remove_review(self, message_id):
        self.repo.remove_review(message_id)

    def get_reviews(self):
        return self.repo.get_reviews()

    def save_balance_decision(self, state):
        self.repo.upsert_balance_decision(state)

    def remove_balance_decision(self, message_id):
        self.repo.remove_balance_decision(message_id)

    def get_balance_decisions(self):
        return self.repo.get_balance_decisions()
