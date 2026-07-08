from repositories.balance_repository import BalanceRepository
from repositories.operation_repository import OperationRepository


class BalanceService:
    def __init__(self):
        self.repo = BalanceRepository()
        self.operation_repo = OperationRepository()

    def get_guild_parts(self, guild):
        if hasattr(guild, "id"):
            return guild.id, getattr(guild, "name", None)

        return guild, None

    def register_guild(self, guild):
        guild_id, guild_name = self.get_guild_parts(guild)
        if guild_name:
            self.repo.update_guild_name(guild_id, guild_name)
            self.operation_repo.update_guild_name(guild_id, guild_name)

    def get_balance(self, guild, user_id):
        guild_id, guild_name = self.get_guild_parts(guild)
        return self.repo.get_balance(guild_id, user_id, guild_name)

    def modify(self, guild, user_id, amount, key, add=True):
        guild_id, guild_name = self.get_guild_parts(guild)
        self.repo.modify_balance(guild_id, user_id, amount, key, add, guild_name)

    def resolve_existing_user(self, guild, identifier):
        guild_id, _ = self.get_guild_parts(guild)
        return self.repo.resolve_existing_user(guild_id, identifier)

    def search_existing_users(self, guild, query, limit=25):
        guild_id, _ = self.get_guild_parts(guild)
        return self.repo.search_existing_users(guild_id, query, limit)

    def modify_existing(self, guild, user_id, amount, key, add=True):
        guild_id, _ = self.get_guild_parts(guild)
        return self.repo.modify_existing_balance(guild_id, user_id, amount, key, add)

    def get_ranking(self, guild):
        guild_id, guild_name = self.get_guild_parts(guild)
        return self.repo.get_ranking(guild_id, guild_name)

    def log_operation(self, guild, operation):
        guild_id, guild_name = self.get_guild_parts(guild)
        self.repo.update_user_name(guild_id, operation.get("player_id"), operation.get("player"), guild_name)
        self.operation_repo.append(guild_id, operation, guild_name)

    def get_operations(self, guild):
        guild_id, guild_name = self.get_guild_parts(guild)
        if guild_name:
            self.operation_repo.update_guild_name(guild_id, guild_name)
        return self.operation_repo.get_by_guild(guild_id)
