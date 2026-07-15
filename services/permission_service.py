from dataclasses import dataclass

from repositories.permission_repository import PermissionRepository


PERMISSION_ECONOMY = "economia"
PERMISSION_PING = "ping"
PERMISSION_TEMPLATES = "plantillas"
PERMISSION_REPORTS = "informes"
PERMISSION_TICKETS = "tickets"
PERMISSION_PERMISSIONS = "permisos"
PERMISSION_GLOBAL = "global"
PERMISSION_ADMIN_PANEL_SYSTEM = "system.admin_panel.access"

PERMISSION_VIEW_ECONOMY = "view.economy"
PERMISSION_VIEW_TEMPLATES = "view.templates"
PERMISSION_VIEW_TICKETS = "view.tickets"
PERMISSION_VIEW_FINES = "view.fines"
PERMISSION_VIEW_AUDIT = "view.audit"
PERMISSION_VIEW_PERMISSIONS = "view.permissions"
PERMISSION_VIEW_REGISTRATION = "view.registration"
PERMISSION_VIEW_LOOT = "view.loot"
PERMISSION_VIEW_REPORT_CALCULATOR = "view.report_calculator"
PERMISSION_VIEW_WELCOME = "view.welcome"

PERMISSION_ECONOMY_BALANCE_VIEW = "economy.balance.view"
PERMISSION_ECONOMY_BALANCE_EDIT = "economy.balance.edit"
PERMISSION_ECONOMY_EXPORT = "economy.export"

PERMISSION_PING_USE = "ping.use"

PERMISSION_TEMPLATES_VIEW = "templates.view"
PERMISSION_TEMPLATES_CREATE = "templates.create"
PERMISSION_TEMPLATES_EDIT = "templates.edit"
PERMISSION_TEMPLATES_DELETE = "templates.delete"
PERMISSION_TEMPLATES_EXPORT = "templates.export"

PERMISSION_TICKETS_PANEL_EDIT = "tickets.panel.edit"
PERMISSION_TICKETS_RECORDS_VIEW = "tickets.records.view"
PERMISSION_TICKETS_RECORDS_CLAIM = "tickets.records.claim"
PERMISSION_TICKETS_RECORDS_ADD_MEMBER = "tickets.records.add_member"
PERMISSION_TICKETS_RECORDS_CLOSE = "tickets.records.close"
PERMISSION_TICKETS_RECORDS_REOPEN = "tickets.records.reopen"
PERMISSION_TICKETS_RECORDS_DELETE = "tickets.records.delete"
PERMISSION_TICKETS_RECORDS_TRANSCRIPT = "tickets.records.transcript"
PERMISSION_TICKETS_EXPORT = "tickets.export"

PERMISSION_FINES_CONFIG_EDIT = "fines.config.edit"
PERMISSION_FINES_RECORDS_MANAGE = "fines.records.manage"

PERMISSION_AUDIT_CONFIG_EDIT = "audit.config.edit"
PERMISSION_AUDIT_EVENTS_VIEW = "audit.events.view"

PERMISSION_REGISTRATION_CONFIG_EDIT = "registration.config.edit"
PERMISSION_REGISTRATION_RECORDS_REVIEW = "registration.records.review"

PERMISSION_LOOT_USE = "loot.use"

PERMISSION_REPORT_CALCULATOR_USE = "report_calculator.use"

PERMISSION_WELCOME_CONFIG_EDIT = "welcome.config.edit"

PERMISSION_ROLES_VIEW = "permissions.roles.view"
PERMISSION_ROLES_EDIT = "permissions.roles.edit"
PERMISSION_MANAGE_ECONOMY = "permissions.manage.economy"
PERMISSION_MANAGE_TEMPLATES = "permissions.manage.templates"
PERMISSION_MANAGE_TICKETS = "permissions.manage.tickets"
PERMISSION_MANAGE_FINES = "permissions.manage.fines"
PERMISSION_MANAGE_AUDIT = "permissions.manage.audit"
PERMISSION_MANAGE_PERMISSIONS = "permissions.manage.permissions"
PERMISSION_MANAGE_REGISTRATION = "permissions.manage.registration"
PERMISSION_MANAGE_LOOT = "permissions.manage.loot"
PERMISSION_MANAGE_REPORT_CALCULATOR = "permissions.manage.report_calculator"
PERMISSION_MANAGE_WELCOME = "permissions.manage.welcome"

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
MODULE_ADMIN_PANEL = "admin_panel"
MODULE_PING = "ping"
MODULE_REPORTS = "reports"
MODULE_LOOT = "loot"
MODULE_REPORT_CALCULATOR = "report_calculator"
MODULE_WELCOME = "welcome"

EDIT_SCOPE_ECONOMY = "economy"
EDIT_SCOPE_TEMPLATES = "templates"
EDIT_SCOPE_TICKETS = "tickets"
EDIT_SCOPE_FINES = "fines"
EDIT_SCOPE_AUDIT = "audit"
EDIT_SCOPE_PERMISSIONS = "permissions"
EDIT_SCOPE_REGISTRATION = "registration"
EDIT_SCOPE_LOOT = "loot"
EDIT_SCOPE_REPORT_CALCULATOR = "report_calculator"
EDIT_SCOPE_WELCOME = "welcome"


@dataclass(frozen=True)
class PermissionDefinition:
    key: str
    label: str
    description: str
    module: str
    scope: str
    category: str
    assignable: bool = True
    system_only: bool = False
    editable_scope: str = ""


def _permission(
    key,
    label,
    description,
    *,
    module,
    scope,
    category,
    assignable=True,
    system_only=False,
    editable_scope="",
):
    return PermissionDefinition(
        key=key,
        label=label,
        description=description,
        module=module,
        scope=scope,
        category=category,
        assignable=assignable,
        system_only=system_only,
        editable_scope=editable_scope or module,
    )


PERMISSION_CATALOG = (
    _permission(
        PERMISSION_GLOBAL,
        "Global",
        "Conserva acceso total heredado del sistema anterior, incluido el panel administrativo.",
        module="system",
        scope="system",
        category="system",
        assignable=False,
        system_only=True,
        editable_scope="system",
    ),
    _permission(
        PERMISSION_ADMIN_PANEL_SYSTEM,
        "Panel Administrativo",
        "Acceso especial heredado para el panel administrativo.",
        module=MODULE_ADMIN_PANEL,
        scope="system",
        category="system",
        assignable=False,
        system_only=True,
        editable_scope="system",
    ),
    _permission(
        PERMISSION_VIEW_ECONOMY,
        "Ver economia",
        "Habilita la vista de economia del dashboard.",
        module=MODULE_ECONOMY,
        scope="view",
        category="Vistas",
        editable_scope=EDIT_SCOPE_ECONOMY,
    ),
    _permission(
        PERMISSION_ECONOMY_BALANCE_VIEW,
        "Ver balances",
        "Permite consultar balances y registros de economia.",
        module=MODULE_ECONOMY,
        scope="action",
        category="Economia",
        editable_scope=EDIT_SCOPE_ECONOMY,
    ),
    _permission(
        PERMISSION_ECONOMY_BALANCE_EDIT,
        "Editar balances",
        "Permite agregar o quitar balance desde comandos y dashboard.",
        module=MODULE_ECONOMY,
        scope="action",
        category="Economia",
        editable_scope=EDIT_SCOPE_ECONOMY,
    ),
    _permission(
        PERMISSION_ECONOMY_EXPORT,
        "Exportar economia",
        "Permite exportar balances, registros y reportes de economia.",
        module=MODULE_EXPORT_ECONOMY,
        scope="action",
        category="Economia",
        editable_scope=EDIT_SCOPE_ECONOMY,
    ),
    _permission(
        PERMISSION_PING_USE,
        "Usar pings",
        "Permite publicar y administrar pings avalonianos.",
        module=MODULE_PING,
        scope="action",
        category="Economia",
        editable_scope=EDIT_SCOPE_ECONOMY,
    ),
    _permission(
        PERMISSION_VIEW_TEMPLATES,
        "Ver plantillas",
        "Habilita la vista de plantillas del dashboard.",
        module=MODULE_TEMPLATES,
        scope="view",
        category="Vistas",
        editable_scope=EDIT_SCOPE_TEMPLATES,
    ),
    _permission(
        PERMISSION_TEMPLATES_VIEW,
        "Listar plantillas",
        "Permite ver el catalogo de plantillas y su ayuda.",
        module=MODULE_TEMPLATES,
        scope="action",
        category="Plantillas",
        editable_scope=EDIT_SCOPE_TEMPLATES,
    ),
    _permission(
        PERMISSION_TEMPLATES_CREATE,
        "Crear plantillas",
        "Permite crear nuevas plantillas de ping.",
        module=MODULE_TEMPLATES,
        scope="action",
        category="Plantillas",
        editable_scope=EDIT_SCOPE_TEMPLATES,
    ),
    _permission(
        PERMISSION_TEMPLATES_EDIT,
        "Editar plantillas",
        "Permite guardar cambios sobre plantillas existentes.",
        module=MODULE_TEMPLATES,
        scope="action",
        category="Plantillas",
        editable_scope=EDIT_SCOPE_TEMPLATES,
    ),
    _permission(
        PERMISSION_TEMPLATES_DELETE,
        "Eliminar plantillas",
        "Permite eliminar plantillas guardadas del servidor.",
        module=MODULE_TEMPLATES,
        scope="action",
        category="Plantillas",
        editable_scope=EDIT_SCOPE_TEMPLATES,
    ),
    _permission(
        PERMISSION_TEMPLATES_EXPORT,
        "Exportar plantillas",
        "Permite exportar datos vinculados a plantillas y tickets.",
        module=MODULE_EXPORT_TEMPLATES,
        scope="action",
        category="Plantillas",
        editable_scope=EDIT_SCOPE_TEMPLATES,
    ),
    _permission(
        PERMISSION_VIEW_TICKETS,
        "Ver tickets",
        "Habilita la vista de tickets del dashboard.",
        module=MODULE_TICKETS,
        scope="view",
        category="Vistas",
        editable_scope=EDIT_SCOPE_TICKETS,
    ),
    _permission(
        PERMISSION_TICKETS_PANEL_EDIT,
        "Editar paneles de tickets",
        "Permite crear o actualizar paneles y mensajes de tickets.",
        module=MODULE_TICKETS,
        scope="action",
        category="Tickets",
        editable_scope=EDIT_SCOPE_TICKETS,
    ),
    _permission(
        PERMISSION_TICKETS_RECORDS_VIEW,
        "Ver registros de tickets",
        "Permite ver tickets, transcriptos y actividad asociada.",
        module=MODULE_TICKETS,
        scope="action",
        category="Tickets",
        editable_scope=EDIT_SCOPE_TICKETS,
    ),
    _permission(
        PERMISSION_TICKETS_RECORDS_CLAIM,
        "Tomar tickets",
        "Permite reclamar tickets activos.",
        module=MODULE_TICKETS,
        scope="action",
        category="Tickets",
        editable_scope=EDIT_SCOPE_TICKETS,
    ),
    _permission(
        PERMISSION_TICKETS_RECORDS_ADD_MEMBER,
        "Agregar miembros a tickets",
        "Permite sumar miembros adicionales a un ticket.",
        module=MODULE_TICKETS,
        scope="action",
        category="Tickets",
        editable_scope=EDIT_SCOPE_TICKETS,
    ),
    _permission(
        PERMISSION_TICKETS_RECORDS_CLOSE,
        "Cerrar tickets",
        "Permite cerrar tickets desde Discord.",
        module=MODULE_TICKETS,
        scope="action",
        category="Tickets",
        editable_scope=EDIT_SCOPE_TICKETS,
    ),
    _permission(
        PERMISSION_TICKETS_RECORDS_REOPEN,
        "Reabrir tickets",
        "Permite reabrir tickets ya cerrados.",
        module=MODULE_TICKETS,
        scope="action",
        category="Tickets",
        editable_scope=EDIT_SCOPE_TICKETS,
    ),
    _permission(
        PERMISSION_TICKETS_RECORDS_DELETE,
        "Eliminar tickets",
        "Permite eliminar tickets o sus registros finales.",
        module=MODULE_TICKETS,
        scope="action",
        category="Tickets",
        editable_scope=EDIT_SCOPE_TICKETS,
    ),
    _permission(
        PERMISSION_TICKETS_RECORDS_TRANSCRIPT,
        "Transcribir tickets",
        "Permite guardar transcripciones finales en el dashboard.",
        module=MODULE_TICKETS,
        scope="action",
        category="Tickets",
        editable_scope=EDIT_SCOPE_TICKETS,
    ),
    _permission(
        PERMISSION_TICKETS_EXPORT,
        "Exportar tickets",
        "Permite exportar tickets a JSON.",
        module=MODULE_EXPORT_TICKETS,
        scope="action",
        category="Tickets",
        editable_scope=EDIT_SCOPE_TICKETS,
    ),
    _permission(
        PERMISSION_VIEW_FINES,
        "Ver multas",
        "Habilita la vista de multas del dashboard.",
        module=MODULE_FINES,
        scope="view",
        category="Vistas",
        editable_scope=EDIT_SCOPE_FINES,
    ),
    _permission(
        PERMISSION_FINES_CONFIG_EDIT,
        "Editar configuracion de multas",
        "Permite actualizar canales y roles de multas.",
        module=MODULE_FINES,
        scope="action",
        category="Multas",
        editable_scope=EDIT_SCOPE_FINES,
    ),
    _permission(
        PERMISSION_FINES_RECORDS_MANAGE,
        "Gestionar multas",
        "Permite operar tickets de multas y su flujo asociado.",
        module=MODULE_FINES,
        scope="action",
        category="Multas",
        editable_scope=EDIT_SCOPE_FINES,
    ),
    _permission(
        PERMISSION_VIEW_AUDIT,
        "Ver auditoria",
        "Habilita la vista de auditoria del dashboard.",
        module=MODULE_AUDIT,
        scope="view",
        category="Vistas",
        editable_scope=EDIT_SCOPE_AUDIT,
    ),
    _permission(
        PERMISSION_AUDIT_CONFIG_EDIT,
        "Editar auditoria",
        "Permite cambiar la configuracion de auditoria.",
        module=MODULE_AUDIT,
        scope="action",
        category="Auditoria",
        editable_scope=EDIT_SCOPE_AUDIT,
    ),
    _permission(
        PERMISSION_AUDIT_EVENTS_VIEW,
        "Ver eventos de auditoria",
        "Permite revisar eventos recientes del servidor.",
        module=MODULE_AUDIT,
        scope="action",
        category="Auditoria",
        editable_scope=EDIT_SCOPE_AUDIT,
    ),
    _permission(
        PERMISSION_VIEW_PERMISSIONS,
        "Ver permisos",
        "Habilita la vista de permisos del dashboard.",
        module=MODULE_PERMISSIONS,
        scope="view",
        category="Vistas",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_ROLES_VIEW,
        "Ver asignaciones de permisos",
        "Permite consultar permisos asignados por rol.",
        module=MODULE_PERMISSIONS,
        scope="permission_management",
        category="Gestion de permisos",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_ROLES_EDIT,
        "Editar asignaciones de permisos",
        "Permite agregar o quitar permisos desde dashboard o comandos.",
        module=MODULE_PERMISSIONS,
        scope="permission_management",
        category="Gestion de permisos",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_MANAGE_ECONOMY,
        "Gestionar permisos de economia",
        "Permite editar permisos de economia para otros roles.",
        module=MODULE_PERMISSIONS,
        scope="permission_management",
        category="Gestion de permisos",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_MANAGE_TEMPLATES,
        "Gestionar permisos de plantillas",
        "Permite editar permisos de plantillas para otros roles.",
        module=MODULE_PERMISSIONS,
        scope="permission_management",
        category="Gestion de permisos",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_MANAGE_TICKETS,
        "Gestionar permisos de tickets",
        "Permite editar permisos de tickets para otros roles.",
        module=MODULE_PERMISSIONS,
        scope="permission_management",
        category="Gestion de permisos",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_MANAGE_FINES,
        "Gestionar permisos de multas",
        "Permite editar permisos de multas para otros roles.",
        module=MODULE_PERMISSIONS,
        scope="permission_management",
        category="Gestion de permisos",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_MANAGE_AUDIT,
        "Gestionar permisos de auditoria",
        "Permite editar permisos de auditoria para otros roles.",
        module=MODULE_PERMISSIONS,
        scope="permission_management",
        category="Gestion de permisos",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_MANAGE_PERMISSIONS,
        "Gestionar permisos de permisos",
        "Permite editar los scopes del propio sistema de permisos.",
        module=MODULE_PERMISSIONS,
        scope="permission_management",
        category="Gestion de permisos",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_MANAGE_REGISTRATION,
        "Gestionar permisos de registro",
        "Permite editar permisos de registro Albion para otros roles.",
        module=MODULE_PERMISSIONS,
        scope="permission_management",
        category="Gestion de permisos",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_MANAGE_LOOT,
        "Gestionar permisos de loot",
        "Permite editar permisos del analizador de loot.",
        module=MODULE_PERMISSIONS,
        scope="permission_management",
        category="Gestion de permisos",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_MANAGE_REPORT_CALCULATOR,
        "Gestionar permisos de calculadora",
        "Permite editar permisos de la calculadora de reportes.",
        module=MODULE_PERMISSIONS,
        scope="permission_management",
        category="Gestion de permisos",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_MANAGE_WELCOME,
        "Gestionar permisos de bienvenidas",
        "Permite editar permisos de la vista de bienvenidas.",
        module=MODULE_PERMISSIONS,
        scope="permission_management",
        category="Gestion de permisos",
        editable_scope=EDIT_SCOPE_PERMISSIONS,
    ),
    _permission(
        PERMISSION_VIEW_REGISTRATION,
        "Ver registro Albion",
        "Habilita la vista de registro Albion del dashboard.",
        module=MODULE_ALBION_REGISTRATION,
        scope="view",
        category="Vistas",
        editable_scope=EDIT_SCOPE_REGISTRATION,
    ),
    _permission(
        PERMISSION_REGISTRATION_CONFIG_EDIT,
        "Editar registro Albion",
        "Permite actualizar la configuracion de registro Albion.",
        module=MODULE_ALBION_REGISTRATION,
        scope="action",
        category="Registro Albion",
        editable_scope=EDIT_SCOPE_REGISTRATION,
    ),
    _permission(
        PERMISSION_REGISTRATION_RECORDS_REVIEW,
        "Revisar registro Albion",
        "Permite revisar solicitudes y registros sincronizados.",
        module=MODULE_ALBION_REGISTRATION,
        scope="action",
        category="Registro Albion",
        editable_scope=EDIT_SCOPE_REGISTRATION,
    ),
    _permission(
        PERMISSION_VIEW_LOOT,
        "Ver loot",
        "Habilita la vista del analizador de loot.",
        module=MODULE_LOOT,
        scope="view",
        category="Vistas",
        editable_scope=EDIT_SCOPE_LOOT,
    ),
    _permission(
        PERMISSION_LOOT_USE,
        "Usar analizador de loot",
        "Permite cargar y normalizar archivos de loot.",
        module=MODULE_LOOT,
        scope="action",
        category="Loot",
        editable_scope=EDIT_SCOPE_LOOT,
    ),
    _permission(
        PERMISSION_VIEW_REPORT_CALCULATOR,
        "Ver calculadora",
        "Habilita la vista de calculadora de reportes.",
        module=MODULE_REPORT_CALCULATOR,
        scope="view",
        category="Vistas",
        editable_scope=EDIT_SCOPE_REPORT_CALCULATOR,
    ),
    _permission(
        PERMISSION_REPORT_CALCULATOR_USE,
        "Usar calculadora",
        "Permite abrir la calculadora y previsualizar informes manuales.",
        module=MODULE_REPORT_CALCULATOR,
        scope="action",
        category="Calculadora",
        editable_scope=EDIT_SCOPE_REPORT_CALCULATOR,
    ),
    _permission(
        PERMISSION_VIEW_WELCOME,
        "Ver bienvenidas",
        "Habilita la vista de bienvenida del dashboard.",
        module=MODULE_WELCOME,
        scope="view",
        category="Vistas",
        editable_scope=EDIT_SCOPE_WELCOME,
    ),
    _permission(
        PERMISSION_WELCOME_CONFIG_EDIT,
        "Editar bienvenidas",
        "Reserva el scope para futura configuracion de bienvenida.",
        module=MODULE_WELCOME,
        scope="action",
        category="Bienvenidas",
        editable_scope=EDIT_SCOPE_WELCOME,
    ),
)

PERMISSION_DEFINITION_BY_KEY = {
    definition.key: definition
    for definition in PERMISSION_CATALOG
}

EDIT_SCOPE_MANAGER_PERMISSION = {
    EDIT_SCOPE_ECONOMY: PERMISSION_MANAGE_ECONOMY,
    EDIT_SCOPE_TEMPLATES: PERMISSION_MANAGE_TEMPLATES,
    EDIT_SCOPE_TICKETS: PERMISSION_MANAGE_TICKETS,
    EDIT_SCOPE_FINES: PERMISSION_MANAGE_FINES,
    EDIT_SCOPE_AUDIT: PERMISSION_MANAGE_AUDIT,
    EDIT_SCOPE_PERMISSIONS: PERMISSION_MANAGE_PERMISSIONS,
    EDIT_SCOPE_REGISTRATION: PERMISSION_MANAGE_REGISTRATION,
    EDIT_SCOPE_LOOT: PERMISSION_MANAGE_LOOT,
    EDIT_SCOPE_REPORT_CALCULATOR: PERMISSION_MANAGE_REPORT_CALCULATOR,
    EDIT_SCOPE_WELCOME: PERMISSION_MANAGE_WELCOME,
}

LEGACY_PERMISSION_EXPANSIONS = {
    PERMISSION_ECONOMY: (
        PERMISSION_VIEW_ECONOMY,
        PERMISSION_ECONOMY_BALANCE_VIEW,
        PERMISSION_ECONOMY_BALANCE_EDIT,
        PERMISSION_ECONOMY_EXPORT,
        PERMISSION_PING_USE,
    ),
    PERMISSION_PING: (
        PERMISSION_PING_USE,
    ),
    PERMISSION_TEMPLATES: (
        PERMISSION_VIEW_TEMPLATES,
        PERMISSION_TEMPLATES_VIEW,
        PERMISSION_TEMPLATES_CREATE,
        PERMISSION_TEMPLATES_EDIT,
        PERMISSION_TEMPLATES_DELETE,
        PERMISSION_TEMPLATES_EXPORT,
    ),
    PERMISSION_REPORTS: (
        PERMISSION_VIEW_FINES,
        PERMISSION_FINES_RECORDS_MANAGE,
        PERMISSION_VIEW_REGISTRATION,
        PERMISSION_REGISTRATION_CONFIG_EDIT,
        PERMISSION_REGISTRATION_RECORDS_REVIEW,
        PERMISSION_VIEW_LOOT,
        PERMISSION_LOOT_USE,
        PERMISSION_VIEW_REPORT_CALCULATOR,
        PERMISSION_REPORT_CALCULATOR_USE,
    ),
    PERMISSION_TICKETS: (
        PERMISSION_VIEW_TICKETS,
        PERMISSION_TICKETS_PANEL_EDIT,
        PERMISSION_TICKETS_RECORDS_VIEW,
        PERMISSION_TICKETS_RECORDS_CLAIM,
        PERMISSION_TICKETS_RECORDS_ADD_MEMBER,
        PERMISSION_TICKETS_RECORDS_CLOSE,
        PERMISSION_TICKETS_RECORDS_REOPEN,
        PERMISSION_TICKETS_RECORDS_DELETE,
        PERMISSION_TICKETS_RECORDS_TRANSCRIPT,
        PERMISSION_TICKETS_EXPORT,
        PERMISSION_VIEW_FINES,
        PERMISSION_FINES_RECORDS_MANAGE,
    ),
    PERMISSION_PERMISSIONS: (
        PERMISSION_VIEW_PERMISSIONS,
        PERMISSION_ROLES_VIEW,
        PERMISSION_ROLES_EDIT,
        PERMISSION_MANAGE_ECONOMY,
        PERMISSION_MANAGE_TEMPLATES,
        PERMISSION_MANAGE_TICKETS,
        PERMISSION_MANAGE_FINES,
        PERMISSION_MANAGE_AUDIT,
        PERMISSION_MANAGE_PERMISSIONS,
        PERMISSION_MANAGE_REGISTRATION,
        PERMISSION_MANAGE_LOOT,
        PERMISSION_MANAGE_REPORT_CALCULATOR,
        PERMISSION_MANAGE_WELCOME,
        PERMISSION_VIEW_AUDIT,
        PERMISSION_AUDIT_CONFIG_EDIT,
        PERMISSION_AUDIT_EVENTS_VIEW,
        PERMISSION_ADMIN_PANEL_SYSTEM,
    ),
}

BOT_PERMISSION_DEFINITIONS = [
    (definition.key, definition.label, definition.description)
    for definition in PERMISSION_CATALOG
]

BOT_PERMISSION_LABELS = {
    definition.key: definition.label
    for definition in PERMISSION_CATALOG
}

BOT_PERMISSION_KEYS = {
    definition.key
    for definition in PERMISSION_CATALOG
}

ASSIGNABLE_PERMISSION_KEYS = {
    definition.key
    for definition in PERMISSION_CATALOG
    if definition.assignable and not definition.system_only
}

PUBLIC_PERMISSION_DEFINITIONS = tuple(
    definition
    for definition in PERMISSION_CATALOG
    if not definition.system_only
)

PUBLIC_PERMISSION_KEYS = {
    definition.key
    for definition in PUBLIC_PERMISSION_DEFINITIONS
}

MODULE_PERMISSION_RULES = {
    MODULE_ECONOMY: (PERMISSION_VIEW_ECONOMY,),
    MODULE_TICKETS: (PERMISSION_VIEW_TICKETS,),
    MODULE_FINES: (PERMISSION_VIEW_FINES,),
    MODULE_AUDIT: (PERMISSION_VIEW_AUDIT,),
    MODULE_TEMPLATES: (PERMISSION_VIEW_TEMPLATES,),
    MODULE_ALBION_REGISTRATION: (PERMISSION_VIEW_REGISTRATION,),
    MODULE_EXPORT_ECONOMY: (PERMISSION_ECONOMY_EXPORT,),
    MODULE_EXPORT_TEMPLATES: (PERMISSION_TEMPLATES_EXPORT,),
    MODULE_EXPORT_TICKETS: (PERMISSION_TICKETS_EXPORT,),
    MODULE_CONFIGURATION: (PERMISSION_AUDIT_CONFIG_EDIT, PERMISSION_FINES_CONFIG_EDIT),
    MODULE_PERMISSIONS: (
        PERMISSION_VIEW_PERMISSIONS,
        PERMISSION_ROLES_VIEW,
        PERMISSION_ROLES_EDIT,
        PERMISSION_MANAGE_ECONOMY,
        PERMISSION_MANAGE_TEMPLATES,
        PERMISSION_MANAGE_TICKETS,
        PERMISSION_MANAGE_FINES,
        PERMISSION_MANAGE_AUDIT,
        PERMISSION_MANAGE_PERMISSIONS,
        PERMISSION_MANAGE_REGISTRATION,
        PERMISSION_MANAGE_LOOT,
        PERMISSION_MANAGE_REPORT_CALCULATOR,
        PERMISSION_MANAGE_WELCOME,
    ),
    MODULE_ADMIN_PANEL: (PERMISSION_ADMIN_PANEL_SYSTEM, PERMISSION_GLOBAL),
    MODULE_PING: (PERMISSION_PING_USE,),
    MODULE_REPORTS: (PERMISSION_VIEW_REPORT_CALCULATOR, PERMISSION_VIEW_LOOT),
    MODULE_LOOT: (PERMISSION_VIEW_LOOT,),
    MODULE_REPORT_CALCULATOR: (PERMISSION_VIEW_REPORT_CALCULATOR,),
    MODULE_WELCOME: (PERMISSION_VIEW_WELCOME,),
}

DASHBOARD_SECTION_MODULES = {
    "economy": MODULE_ECONOMY,
    "templates": MODULE_TEMPLATES,
    "tickets": MODULE_TICKETS,
    "fines": MODULE_FINES,
    "audit": MODULE_AUDIT,
    "permissions": MODULE_PERMISSIONS,
    "admin-panel": MODULE_ADMIN_PANEL,
    "registration": MODULE_ALBION_REGISTRATION,
    "loot": MODULE_LOOT,
    "report-calculator": MODULE_REPORT_CALCULATOR,
    "welcome": MODULE_WELCOME,
}

DASHBOARD_GUILD_MODULES = tuple(dict.fromkeys(DASHBOARD_SECTION_MODULES.values()))


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

    @staticmethod
    def normalize_permission_key(permission):
        return str(permission or "").strip().lower()

    @classmethod
    def expand_permission_key(cls, permission):
        normalized = cls.normalize_permission_key(permission)
        if not normalized:
            return ()
        if normalized in LEGACY_PERMISSION_EXPANSIONS:
            return LEGACY_PERMISSION_EXPANSIONS[normalized]
        if normalized in BOT_PERMISSION_KEYS:
            return (normalized,)
        return ()

    @classmethod
    def normalize_permissions(cls, permissions, *, include_system_permissions=True):
        if isinstance(permissions, str):
            permissions = [permissions]
        if not isinstance(permissions, (list, tuple, set)):
            permissions = []

        normalized = []
        for permission in permissions:
            for expanded in cls.expand_permission_key(permission):
                definition = PERMISSION_DEFINITION_BY_KEY.get(expanded)
                if definition is None:
                    continue
                if definition.system_only and not include_system_permissions:
                    continue
                if expanded not in normalized:
                    normalized.append(expanded)

        return normalized

    def get_role_permissions(self, guild_id, *, include_system_permissions=True):
        raw_permissions = self.repo.get_permissions(guild_id)
        normalized_permissions = {}
        migrated = False

        for role_id, permissions in raw_permissions.items():
            expanded = self.normalize_permissions(permissions, include_system_permissions=True)
            if expanded:
                normalized_permissions[str(role_id)] = expanded
            if list(permissions) != expanded:
                migrated = True

        if migrated:
            self.repo.set_guild_permissions(guild_id, normalized_permissions)

        if include_system_permissions:
            return normalized_permissions

        visible_permissions = {}
        for role_id, permissions in normalized_permissions.items():
            cleaned = [
                permission
                for permission in permissions
                if permission in PUBLIC_PERMISSION_KEYS
            ]
            if cleaned:
                visible_permissions[role_id] = cleaned
        return visible_permissions

    def get_hidden_role_permissions(self, guild_id):
        visible_permissions = self.get_role_permissions(guild_id, include_system_permissions=False)
        all_permissions = self.get_role_permissions(guild_id, include_system_permissions=True)
        hidden_permissions = {}
        for role_id, permissions in all_permissions.items():
            visible = set(visible_permissions.get(role_id, []))
            hidden = [
                permission
                for permission in permissions
                if permission not in visible
            ]
            if hidden:
                hidden_permissions[str(role_id)] = hidden
        return hidden_permissions

    def list_public_permissions(self):
        return PUBLIC_PERMISSION_DEFINITIONS

    def list_assignable_permissions(self):
        return tuple(
            definition
            for definition in PUBLIC_PERMISSION_DEFINITIONS
            if definition.assignable
        )

    def get_required_permissions(self, module_key):
        return tuple(MODULE_PERMISSION_RULES.get(str(module_key or ""), ()))

    def has_any_permission(self, guild_id, role_ids, required_permissions):
        guild_id = str(guild_id or "")
        if not guild_id or not role_ids or not required_permissions:
            return False

        role_permissions = self.get_role_permissions(guild_id)
        required = {
            self.normalize_permission_key(permission)
            for permission in required_permissions
            if self.normalize_permission_key(permission)
        }
        if not required:
            return False

        for role_id in role_ids:
            assigned = set(role_permissions.get(str(role_id), []))
            if PERMISSION_GLOBAL in assigned:
                return True
            if assigned & required:
                return True
        return False

    def has_permission(self, guild_id, member, permission):
        if self.is_administrator(member):
            return True

        required_permissions = self.expand_permission_key(permission)
        if not required_permissions:
            return False

        role_permissions = self.get_role_permissions(guild_id)
        for role in getattr(member, "roles", []) or []:
            assigned = set(role_permissions.get(str(role.id), []))
            if PERMISSION_GLOBAL in assigned or assigned.intersection(required_permissions):
                return True
        return False

    def has_module_access(
        self,
        guild_id,
        module_key,
        *,
        member=None,
        role_ids=None,
        is_admin=False,
        required_permissions=None,
    ):
        effective_permissions = tuple(required_permissions or self.get_required_permissions(module_key))
        if not effective_permissions:
            return False

        if member is not None and self.is_administrator(member):
            return True
        if is_admin:
            return True

        resolved_role_ids = role_ids
        if resolved_role_ids is None and member is not None:
            resolved_role_ids = [
                getattr(role, "id", role)
                for role in getattr(member, "roles", []) or []
            ]

        return self.has_any_permission(guild_id, resolved_role_ids or [], effective_permissions)

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

    def can_view_section(self, guild_id, section_key, *, member=None, role_ids=None, is_admin=False):
        module_key = DASHBOARD_SECTION_MODULES.get(str(section_key or ""))
        if not module_key:
            return False
        return self.has_module_access(
            guild_id,
            module_key,
            member=member,
            role_ids=role_ids,
            is_admin=is_admin,
        )

    def manageable_edit_scopes(self, guild_id, *, member=None, role_ids=None, is_admin=False):
        if member is not None and self.is_administrator(member):
            return set(EDIT_SCOPE_MANAGER_PERMISSION)
        if is_admin:
            return set(EDIT_SCOPE_MANAGER_PERMISSION)

        if not self.has_module_access(
            guild_id,
            MODULE_PERMISSIONS,
            member=member,
            role_ids=role_ids,
            is_admin=is_admin,
            required_permissions=(PERMISSION_ROLES_EDIT,),
        ):
            return set()

        resolved_role_ids = role_ids
        if resolved_role_ids is None and member is not None:
            resolved_role_ids = [getattr(role, "id", role) for role in getattr(member, "roles", []) or []]

        editable_scopes = set()
        for scope, manager_permission in EDIT_SCOPE_MANAGER_PERMISSION.items():
            if self.has_any_permission(guild_id, resolved_role_ids or [], (manager_permission,)):
                editable_scopes.add(scope)
        return editable_scopes

    def manageable_permission_keys(self, guild_id, *, member=None, role_ids=None, is_admin=False):
        if member is not None and self.is_administrator(member):
            return ASSIGNABLE_PERMISSION_KEYS
        if is_admin:
            return ASSIGNABLE_PERMISSION_KEYS

        scopes = self.manageable_edit_scopes(
            guild_id,
            member=member,
            role_ids=role_ids,
            is_admin=is_admin,
        )
        if not scopes:
            return set()

        return {
            definition.key
            for definition in self.list_assignable_permissions()
            if definition.editable_scope in scopes
        }

    def can_view_role_permissions(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_PERMISSIONS,
            member=member,
            required_permissions=(PERMISSION_VIEW_PERMISSIONS, PERMISSION_ROLES_VIEW, PERMISSION_ROLES_EDIT),
        )

    def can_edit_role_permissions(self, guild_id, member):
        if self.is_administrator(member):
            return True
        manageable_keys = self.manageable_permission_keys(guild_id, member=member)
        return bool(manageable_keys)

    def can_modify_target_role(self, member, target_role_id):
        if self.is_administrator(member):
            return True

        target_role_id = str(target_role_id or "")
        if not target_role_id:
            return False

        return all(str(getattr(role, "id", "")) != target_role_id for role in getattr(member, "roles", []) or [])

    def validate_role_permission_update(self, guild_id, member, target_role_id, requested_permissions):
        if not self.can_edit_role_permissions(guild_id, member):
            return "No tienes permisos para gestionar roles con permisos."

        if not self.can_modify_target_role(member, target_role_id):
            return "No puedes editar permisos de un rol que ya posees."

        requested_permissions = self.normalize_permissions(
            requested_permissions,
            include_system_permissions=False,
        )
        invalid_permissions = [
            permission
            for permission in requested_permissions
            if permission not in ASSIGNABLE_PERMISSION_KEYS
        ]
        if invalid_permissions:
            return "La seleccion incluye permisos no editables por el sistema."

        manageable_permissions = self.manageable_permission_keys(guild_id, member=member)
        unauthorized_permissions = [
            permission
            for permission in requested_permissions
            if permission not in manageable_permissions
        ]
        if unauthorized_permissions:
            return "Intentaste modificar scopes que no puedes gestionar."

        return None

    def split_permissions_for_storage(self, permissions):
        visible_permissions = self.normalize_permissions(
            permissions,
            include_system_permissions=False,
        )
        hidden_permissions = [
            permission
            for permission in self.normalize_permissions(permissions, include_system_permissions=True)
            if permission not in visible_permissions
        ]
        return visible_permissions, hidden_permissions

    def update_role_permissions(self, guild_id, role_id, permissions):
        role_id = str(role_id or "").strip()
        if not role_id.isdigit():
            return False

        current_permissions = self.get_role_permissions(guild_id, include_system_permissions=True)
        _, hidden_permissions = self.split_permissions_for_storage(current_permissions.get(role_id, []))
        visible_permissions = self.normalize_permissions(permissions, include_system_permissions=False)
        merged_permissions = visible_permissions + [
            permission
            for permission in hidden_permissions
            if permission not in visible_permissions
        ]

        if merged_permissions:
            current_permissions[role_id] = merged_permissions
        else:
            current_permissions.pop(role_id, None)

        self.repo.set_guild_permissions(guild_id, current_permissions)
        return True

    def set_role_permissions(self, guild_id, permissions_by_role, *, preserve_hidden_permissions=None):
        normalized = {}
        preserve_hidden_permissions = preserve_hidden_permissions or {}
        for role_id, visible_permissions in (permissions_by_role or {}).items():
            role_id = str(role_id or "").strip()
            if not role_id.isdigit():
                continue

            visible_permissions = self.normalize_permissions(
                visible_permissions,
                include_system_permissions=False,
            )
            hidden_permissions = self.normalize_permissions(
                preserve_hidden_permissions.get(role_id, []),
                include_system_permissions=True,
            )
            merged_permissions = visible_permissions + [
                permission
                for permission in hidden_permissions
                if permission not in visible_permissions
            ]
            if merged_permissions:
                normalized[role_id] = merged_permissions

        self.repo.set_guild_permissions(guild_id, normalized)

    def can_manage_balance(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_ECONOMY,
            member=member,
            required_permissions=(PERMISSION_ECONOMY_BALANCE_EDIT,),
        )

    def can_view_balance(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_ECONOMY,
            member=member,
            required_permissions=(PERMISSION_ECONOMY_BALANCE_VIEW, PERMISSION_ECONOMY_BALANCE_EDIT),
        )

    def can_manage_ping(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_PING,
            member=member,
            required_permissions=(PERMISSION_PING_USE,),
        )

    def can_view_templates(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_TEMPLATES,
            member=member,
            required_permissions=(PERMISSION_TEMPLATES_VIEW, PERMISSION_VIEW_TEMPLATES),
        )

    def can_create_templates(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_TEMPLATES,
            member=member,
            required_permissions=(PERMISSION_TEMPLATES_CREATE,),
        )

    def can_edit_templates(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_TEMPLATES,
            member=member,
            required_permissions=(PERMISSION_TEMPLATES_EDIT,),
        )

    def can_delete_templates(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_TEMPLATES,
            member=member,
            required_permissions=(PERMISSION_TEMPLATES_DELETE,),
        )

    def can_manage_templates(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_TEMPLATES,
            member=member,
            required_permissions=(
                PERMISSION_TEMPLATES_CREATE,
                PERMISSION_TEMPLATES_EDIT,
                PERMISSION_TEMPLATES_DELETE,
                PERMISSION_TEMPLATES_VIEW,
                PERMISSION_VIEW_TEMPLATES,
            ),
        )

    def can_review_reports(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_REPORT_CALCULATOR,
            member=member,
            required_permissions=(PERMISSION_REPORT_CALCULATOR_USE,),
        )

    def can_manage_tickets(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_TICKETS,
            member=member,
            required_permissions=(
                PERMISSION_TICKETS_PANEL_EDIT,
                PERMISSION_TICKETS_RECORDS_VIEW,
                PERMISSION_TICKETS_RECORDS_CLAIM,
                PERMISSION_TICKETS_RECORDS_ADD_MEMBER,
                PERMISSION_TICKETS_RECORDS_CLOSE,
                PERMISSION_TICKETS_RECORDS_REOPEN,
                PERMISSION_TICKETS_RECORDS_DELETE,
                PERMISSION_TICKETS_RECORDS_TRANSCRIPT,
            ),
        )

    def can_manage_permissions(self, guild_id, member):
        return self.can_edit_role_permissions(guild_id, member)

    def can_manage_fines(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_FINES,
            member=member,
            required_permissions=(PERMISSION_FINES_CONFIG_EDIT, PERMISSION_FINES_RECORDS_MANAGE),
        )

    def can_manage_audit(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_AUDIT,
            member=member,
            required_permissions=(PERMISSION_AUDIT_CONFIG_EDIT, PERMISSION_AUDIT_EVENTS_VIEW),
        )

    def can_manage_albion_registration(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_ALBION_REGISTRATION,
            member=member,
            required_permissions=(PERMISSION_REGISTRATION_CONFIG_EDIT, PERMISSION_REGISTRATION_RECORDS_REVIEW),
        )

    def can_manage_configuration(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_CONFIGURATION, member=member)

    def can_access_admin_panel(self, guild_id, member):
        return self.has_module_access(guild_id, MODULE_ADMIN_PANEL, member=member)

    def can_export_economy(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_EXPORT_ECONOMY,
            member=member,
            required_permissions=(PERMISSION_ECONOMY_EXPORT,),
        )

    def can_export_templates(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_EXPORT_TEMPLATES,
            member=member,
            required_permissions=(PERMISSION_TEMPLATES_EXPORT,),
        )

    def can_export_tickets(self, guild_id, member):
        return self.has_module_access(
            guild_id,
            MODULE_EXPORT_TICKETS,
            member=member,
            required_permissions=(PERMISSION_TICKETS_EXPORT,),
        )

    def add_permission(self, guild_id, role_id, permission):
        normalized_permission = self.normalize_permission_key(permission)
        if normalized_permission not in ASSIGNABLE_PERMISSION_KEYS:
            return False

        current_permissions = self.get_role_permissions(guild_id, include_system_permissions=True)
        role_permissions = current_permissions.get(str(role_id), [])
        visible_permissions = self.normalize_permissions(
            role_permissions,
            include_system_permissions=False,
        )
        hidden_permissions = [
            value
            for value in role_permissions
            if value not in visible_permissions
        ]
        if normalized_permission in visible_permissions:
            return False

        visible_permissions.append(normalized_permission)
        current_permissions[str(role_id)] = visible_permissions + hidden_permissions
        self.repo.set_guild_permissions(guild_id, current_permissions)
        return True

    def remove_permission(self, guild_id, role_id, permission):
        normalized_permission = self.normalize_permission_key(permission)
        if normalized_permission not in ASSIGNABLE_PERMISSION_KEYS:
            return False

        current_permissions = self.get_role_permissions(guild_id, include_system_permissions=True)
        role_id = str(role_id)
        if role_id not in current_permissions:
            return False

        current_values = current_permissions.get(role_id, [])
        visible_permissions = self.normalize_permissions(
            current_values,
            include_system_permissions=False,
        )
        hidden_permissions = [
            value
            for value in current_values
            if value not in visible_permissions
        ]
        if normalized_permission not in visible_permissions:
            return False

        visible_permissions.remove(normalized_permission)
        merged_permissions = visible_permissions + hidden_permissions
        if merged_permissions:
            current_permissions[role_id] = merged_permissions
        else:
            current_permissions.pop(role_id, None)
        self.repo.set_guild_permissions(guild_id, current_permissions)
        return True
