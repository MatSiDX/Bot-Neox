from repositories.avalonian_repository import AvalonianRepository


class AvalonianService:
    def __init__(self):
        self.repo = AvalonianRepository()

    def log_interaction(self, guild_id, interaction):
        self.repo.append(guild_id, interaction)

    def get_interactions(self, guild_id):
        return self.repo.get_by_guild(guild_id)
