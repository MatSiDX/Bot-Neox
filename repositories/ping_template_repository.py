import json
import os

from repositories.balance_repository import DATA_DIR

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
        with open(PING_TEMPLATES_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

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
        with open(PING_TEMPLATES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def ensure_default_template(self):
        data = self.load()
        if DEFAULT_TEMPLATE_KEY not in data[GLOBAL_TEMPLATES_KEY]:
            data[GLOBAL_TEMPLATES_KEY][DEFAULT_TEMPLATE_KEY] = DEFAULT_PING_TEMPLATE

        self.save(data)

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
        data = self.load()
        guild_templates = data.setdefault(GUILD_TEMPLATES_KEY, {}).setdefault(str(guild_id), {})
        key = str(template_key).lower()
        guild_templates[key] = template
        self.save(data)

    def delete(self, guild_id, template_key):
        key = str(template_key or "").lower()
        data = self.load()
        guild_templates = data.setdefault(GUILD_TEMPLATES_KEY, {}).setdefault(str(guild_id), {})
        if key not in guild_templates:
            return False

        guild_templates.pop(key, None)
        if not guild_templates:
            data.setdefault(GUILD_TEMPLATES_KEY, {}).pop(str(guild_id), None)
        self.save(data)
        return True

    def count_guild_templates(self, guild_id):
        return len(self.get_guild_templates(guild_id))

    def guild_template_exists(self, guild_id, template_key):
        return str(template_key or "").lower() in self.get_guild_templates(guild_id)

    def global_template_exists(self, template_key):
        return str(template_key or "").lower() in self.get_global_templates()
