from repositories.permission_repository import PermissionRepository

PERMISSION_ECONOMY = "economia"
PERMISSION_PING = "ping"
PERMISSION_TEMPLATES = "plantillas"
PERMISSION_REPORTS = "informes"
PERMISSION_PERMISSIONS = "permisos"
PERMISSION_GLOBAL = "global"


class PermissionService:
    def __init__(self):
        self.repo = PermissionRepository()

    def get_role_permissions(self, guild_id):
        return self.repo.get_permissions(guild_id)

    def has_permission(self, guild_id, member, permission):
        if member.guild_permissions.administrator:
            return True

        role_permissions = self.get_role_permissions(guild_id)
        for role in member.roles:
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

    def can_manage_permissions(self, guild_id, member):
        return self.has_permission(guild_id, member, PERMISSION_PERMISSIONS)

    def add_permission(self, guild_id, role_id, permission):
        return self.repo.add_permission(guild_id, role_id, permission)

    def remove_permission(self, guild_id, role_id, permission):
        return self.repo.remove_permission(guild_id, role_id, permission)
