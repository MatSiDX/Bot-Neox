from repositories.permission_repository import PermissionRepository

PERMISSION_ECONOMY = "economia"
PERMISSION_PING = "ping"
PERMISSION_TEMPLATES = "plantillas"
PERMISSION_REPORTS = "informes"
PERMISSION_TICKETS = "tickets"
PERMISSION_PERMISSIONS = "permisos"
PERMISSION_GLOBAL = "global"


class PermissionService:
    def __init__(self):
        self.repo = PermissionRepository()

    @staticmethod
    def is_administrator(member):
        guild_permissions = getattr(member, "guild_permissions", None)
        if bool(getattr(guild_permissions, "administrator", False)):
            return True

        guild = getattr(member, "guild", None)
        if guild is not None and getattr(guild, "owner_id", None) == getattr(member, "id", None):
            return True

        for role in getattr(member, "roles", []) or []:
            role_permissions = getattr(role, "permissions", None)
            if bool(getattr(role_permissions, "administrator", False)):
                return True

        return False

    def get_role_permissions(self, guild_id):
        return self.repo.get_permissions(guild_id)

    def has_permission(self, guild_id, member, permission):
        if self.is_administrator(member):
            return True

        role_permissions = self.get_role_permissions(guild_id)
        for role in getattr(member, "roles", []) or []:
            permissions = role_permissions.get(str(role.id), [])
            if PERMISSION_GLOBAL in permissions or permission in permissions:
                return True

        return False

    def can_manage_balance(self, guild_id, member):
        return self.has_permission(guild_id, member, PERMISSION_ECONOMY)

    def can_manage_ping(self, guild_id, member):
        return self.has_permission(guild_id, member, PERMISSION_PING)

    def can_manage_templates(self, guild_id, member):
        return self.has_permission(guild_id, member, PERMISSION_TEMPLATES)

    def can_review_reports(self, guild_id, member):
        return self.has_permission(guild_id, member, PERMISSION_REPORTS)

    def can_manage_tickets(self, guild_id, member):
        return self.has_permission(guild_id, member, PERMISSION_TICKETS)

    def can_manage_permissions(self, guild_id, member):
        return self.has_permission(guild_id, member, PERMISSION_PERMISSIONS)

    def add_permission(self, guild_id, role_id, permission):
        return self.repo.add_permission(guild_id, role_id, permission)

    def remove_permission(self, guild_id, role_id, permission):
        return self.repo.remove_permission(guild_id, role_id, permission)
