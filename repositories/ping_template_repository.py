import os

from repositories.balance_repository import DATA_DIR
from utils.json_store import mutate_json, read_json, write_json

PING_TEMPLATES_FILE = os.path.join(DATA_DIR, "ping_templates.json")

DEFAULT_TEMPLATE_KEY = "avalonianas"
GLOBAL_TEMPLATES_KEY = "global_templates"
GUILD_TEMPLATES_KEY = "guild_templates"
DEFAULT_PING_TEMPLATE = {
    "key": DEFAULT_TEMPLATE_KEY,
    "name": "Avalonianas",
    "title": "Ava {numero}",
    "title_editable": True,
    "mention": "||@everyone||",
    "join_command": "/join {caller}",
    "caller_slot": "MainTank",
    "roles": [
        "MainTank",
        "OffTank",
        "Cobra",
        "Heal",
        "Falce supp",
        "SC",
        "Dps1",
        "Dps2",
        "DpsX",
        "Looter scout",
    ],
    "slot_format": "> **{index}.{slot}:** {user}",
    "content": "# {title} {mention}\n\n/join {caller}\n\n{slots}\n\n**Que debo lootear?** {loot_link}\n\n**Cupos ocupados:** {occupied}/{total}{status}",
    "loot_link": "https://discord.com/channels/1412293536581419038/1484710223280345118",
    "report_enabled": True,
}


class PingTemplateRepository:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(PING_TEMPLATES_FILE):
            self.save(self.default_storage())
        else:
            self.ensure_default_template()

    def default_storage(self):
        return {
            "version": 2,
            GLOBAL_TEMPLATES_KEY: {DEFAULT_TEMPLATE_KEY: DEFAULT_PING_TEMPLATE},
            GUILD_TEMPLATES_KEY: {},
        }

    def load(self):
        data = read_json(PING_TEMPLATES_FILE, self.default_storage())
        return self.normalize_storage(data)

    def normalize_storage(self, data):
        if isinstance(data, dict) and GLOBAL_TEMPLATES_KEY in data and GUILD_TEMPLATES_KEY in data:
            data.setdefault("version", 2)
            data.setdefault(GLOBAL_TEMPLATES_KEY, {})
            data.setdefault(GUILD_TEMPLATES_KEY, {})
            return data

        if isinstance(data, list):
            legacy_templates = {
                template.get("key", template.get("name", "")).lower(): template
                for template in data
                if isinstance(template, dict)
            }
            return {
                "version": 2,
                GLOBAL_TEMPLATES_KEY: legacy_templates,
                GUILD_TEMPLATES_KEY: {},
            }

        if not isinstance(data, dict):
            return self.default_storage()

        legacy_templates = {
            str(key).lower(): template
            for key, template in data.items()
            if isinstance(template, dict)
        }
        return {
            "version": 2,
            GLOBAL_TEMPLATES_KEY: legacy_templates,
            GUILD_TEMPLATES_KEY: {},
        }

    def save(self, data):
        write_json(PING_TEMPLATES_FILE, data)

    def ensure_default_template(self):
        def mutate(data):
            normalized = self.normalize_storage(data)
            if DEFAULT_TEMPLATE_KEY not in normalized[GLOBAL_TEMPLATES_KEY]:
                normalized[GLOBAL_TEMPLATES_KEY][DEFAULT_TEMPLATE_KEY] = DEFAULT_PING_TEMPLATE
            return normalized

        mutate_json(PING_TEMPLATES_FILE, self.default_storage(), mutate)

    def get_all(self, guild_id):
        data = self.load()
        templates = dict(data.get(GLOBAL_TEMPLATES_KEY, {}))
        templates.update(self.get_guild_templates(guild_id))
        return templates

    def get_global_templates(self):
        return self.load().get(GLOBAL_TEMPLATES_KEY, {})

    def get_guild_templates(self, guild_id):
        data = self.load()
        return data.get(GUILD_TEMPLATES_KEY, {}).get(str(guild_id), {})

    def get(self, guild_id, template_key):
        data = self.load()
        key = str(template_key or DEFAULT_TEMPLATE_KEY).lower()
        guild_templates = data.get(GUILD_TEMPLATES_KEY, {}).get(str(guild_id), {})
        global_templates = data.get(GLOBAL_TEMPLATES_KEY, {})
        return guild_templates.get(key) or global_templates.get(key) or global_templates.get(DEFAULT_TEMPLATE_KEY) or DEFAULT_PING_TEMPLATE

    def upsert(self, guild_id, template_key, template):
        key = str(template_key).lower()

        def mutate(data):
            normalized = self.normalize_storage(data)
            guild_templates = normalized.setdefault(GUILD_TEMPLATES_KEY, {}).setdefault(str(guild_id), {})
            guild_templates[key] = template
            return normalized

        mutate_json(PING_TEMPLATES_FILE, self.default_storage(), mutate)

    def delete(self, guild_id, template_key):
        key = str(template_key or "").lower()
        changed = {"value": False}

        def mutate(data):
            normalized = self.normalize_storage(data)
            guild_templates = normalized.setdefault(GUILD_TEMPLATES_KEY, {}).setdefault(str(guild_id), {})
            if key not in guild_templates:
                return normalized

            guild_templates.pop(key, None)
            if not guild_templates:
                normalized.setdefault(GUILD_TEMPLATES_KEY, {}).pop(str(guild_id), None)
            changed["value"] = True
            return normalized

        mutate_json(PING_TEMPLATES_FILE, self.default_storage(), mutate)
        return changed["value"]

    def count_guild_templates(self, guild_id):
        return len(self.get_guild_templates(guild_id))

    def guild_template_exists(self, guild_id, template_key):
        return str(template_key or "").lower() in self.get_guild_templates(guild_id)

    def global_template_exists(self, template_key):
        return str(template_key or "").lower() in self.get_global_templates()
