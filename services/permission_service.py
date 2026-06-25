from repositories.permission_repository import PermissionRepository

PERMISSION_ECONOMY = "economia"
PERMISSION_PING = "ping"
PERMISSION_TEMPLATES = "plantillas"
PERMISSION_REPORTS = "informes"
PERMISSION_TICKETS = "tickets"
PERMISSION_PERMISSIONS = "permisos"
PERMISSION_GLOBAL = "global"

BOT_PERMISSION_DEFINITIONS = [
    (PERMISSION_ECONOMY, "Balance", "Agregar o quitar balance y exportar datos de economia."),
    (PERMISSION_PING, "Ping", "Usar /ping y /ping-test para publicar pings."),
    (PERMISSION_TEMPLATES, "Plantillas", "Crear, editar, listar y eliminar plantillas de ping."),
    (PERMISSION_REPORTS, "Informes", "Revisar y gestionar informes, avalonianas y registro Albion."),
    (PERMISSION_TICKETS, "Tickets", "Ver y gestionar tickets y media asociada."),
    (PERMISSION_PERMISSIONS, "Permisos", "Administrar permisos y configuraciones sensibles del bot."),
    (PERMISSION_GLOBAL, "Global", "Acceso completo a todos los permisos del bot."),
]

BOT_PERMISSION_LABELS = {
    key: label
    for key, label, _ in BOT_PERMISSION_DEFINITIONS
}

BOT_PERMISSION_KEYS = {
    key
    for key, _, _ in BOT_PERMISSION_DEFINITIONS
}

MODULE_ECONOMY = "economy"
MODULE_TICKETS = "tickets"
MODULE_FINES = "fines"
MODULE_AUDIT = "audit"
MODULE_TEMPLATES = "templates"
MODULE_ALBION_REGISTRATION = "albion_registration"
MODULE_EXPORT_ECONOMY = "export_economy"
MODULE_EXPORT_TEMPLATES = "export_templates"
MODULE_EXPORT_TICKETS = "export_tickets"
MODULE_CONFIGURATION = "configuration"
MODULE_PERMISSIONS = "permissions"
MODULE_PING = "ping"
MODULE_REPORTS = "reports"

# Compatibilidad temporal:
# - multas sigue aceptando tickets o informes, porque hoy ambas areas tocan ese flujo.
# - configuracion sensible y auditoria quedan bajo "permisos" para evitar accesos demasiado amplios.
MODULE_PERMISSION_RULES = {
    MODULE_ECONOMY: (PERMISSION_ECONOMY,),
    MODULE_TICKETS: (PERMISSION_TICKETS,),
    MODULE_FINES: (PERMISSION_REPORTS, PERMISSION_TICKETS),
    MODULE_AUDIT: (PERMISSION_PERMISSIONS,),
    MODULE_TEMPLATES: (PERMISSION_TEMPLATES,),
    MODULE_ALBION_REGISTRATION: (PERMISSION_REPORTS,),
    MODULE_EXPORT_ECONOMY: (PERMISSION_ECONOMY,),
    MODULE_EXPORT_TEMPLATES: (PERMISSION_TEMPLATES,),
    MODULE_EXPORT_TICKETS: (PERMISSION_TICKETS,),
    MODULE_CONFIGURATION: (PERMISSION_PERMISSIONS,),
    MODULE_PERMISSIONS: (PERMISSION_PERMISSIONS,),
    MODULE_PING: (PERMISSION_PING,),
    MODULE_REPORTS: (PERMISSION_REPORTS,),
}

DASHBOARD_SECTION_MODULES = {
    "economy": MODULE_ECONOMY,
    "templates": MODULE_TEMPLATES,
    "tickets": MODULE_TICKETS,
    "audit": MODULE_AUDIT,
    "permissions": MODULE_PERMISSIONS,
    "registration": MODULE_ALBION_REGISTRATION,
}

DASHBOARD_GUILD_MODULES = (
    MODULE_ECONOMY,
    MODULE_TICKETS,
    MODULE_FINES,
    MODULE_AUDIT,
    MODULE_TEMPLATES,
    MODULE_ALBION_REGISTRATION,
    MODULE_PERMISSIONS,
)


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

    def get_required_permissions(self, module_key):
        return tuple(MODULE_PERMISSION_RULES.get(str(module_key or ""), ()))

    def has_any_permission(self, guild_id, role_ids, required_permissions):
        guild_id = str(guild_id or "")
        if not guild_id or not role_ids or not required_permissions:
            return False

        role_permissions = self.get_role_permissions(guild_id)
        required = {str(permission) for permission in required_permissions if str(permission).strip()}
        if not required:
            return False

        for role_id in role_ids:
            assigned = role_permissions.get(str(role_id), [])
            if PERMISSION_GLOBAL in assigned:
                return True
            if any(permission in assigned for permission in required):
                return True
        return False

    def has_permission(self, guild_id, member, permission):
        if self.is_administrator(member):
            return True

        role_permissions = self.get_role_permissions(guild_id)
        for role in getattr(member, "roles", []) or []:
            permissions = role_permissions.get(str(role.id), [])
            if PERMISSION_GLOBAL in permissions or permission in permissions:
                return True
            role_ids = [getattr(role, "id", role) for role in getattr(member, "roles", [])]

        effective_permissions = tuple(required_permissions or self.get_required_permissions(module_key))
        return self.has_any_permission(guild_id, role_ids or [], effective_permissions)

    def has_any_dashboard_access(self, guild_id, *, member=None, role_ids=None, is_admin=False):
        for module_key in DASHBOARD_GUILD_MODULES:
            if self.has_module_access(
                guild_id,
                module_key,
                member=member,
                role_ids=role_ids,
                is_admin=is_admin,
            ):
                return True
        return False

    def can_manage_balance(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_ECONOMY, member=member)

    def can_manage_ping(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_PING, member=member)

    def can_manage_templates(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_TEMPLATES, member=member)

    def can_review_reports(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_REPORTS, member=member)

    def can_manage_tickets(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_TICKETS, member=member)

    def can_manage_permissions(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_PERMISSIONS, member=member)

    def can_manage_fines(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_FINES, member=member)

    def can_manage_audit(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_AUDIT, member=member)

    def can_manage_albion_registration(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_ALBION_REGISTRATION, member=member)

    def can_manage_configuration(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_CONFIGURATION, member=member)

    def can_export_economy(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_EXPORT_ECONOMY, member=member)

    def can_export_templates(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_EXPORT_TEMPLATES, member=member)

    def can_export_tickets(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_EXPORT_TICKETS, member=member)

    def add_permission(self, guild_id, role_id, permission):
        if str(permission or "").strip() not in BOT_PERMISSION_KEYS:
            return False
        return self.repo.add_permission(guild_id, role_id, permission)

    def remove_permission(self, guild_id, role_id, permission):
        if str(permission or "").strip() not in BOT_PERMISSION_KEYS:
            return False
        return self.repo.remove_permission(guild_id, role_id, permission)
