from repositories.active_avalonian_repository import ActiveAvalonianRepository


class ActiveAvalonianService:
    def __init__(self):
        self.repo = ActiveAvalonianRepository()

    def save_state(self, state):
        self.repo.upsert(state)

    def remove_state(self, guild_id, caller_id, numero_ava):
        return self.repo.remove(guild_id, caller_id, numero_ava)

    def get_all_states(self):
        return self.repo.get_all_states()
