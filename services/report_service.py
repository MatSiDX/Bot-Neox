from repositories.report_repository import ReportRepository


class ReportService:
    def __init__(self):
        self.repo = ReportRepository()

    def log_review(self, guild_id, report):
        self.repo.append(guild_id, report)

    def get_reviews(self, guild_id):
        return self.repo.get_by_guild(guild_id)
