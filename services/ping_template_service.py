from copy import deepcopy
import re

from repositories.ping_template_repository import DEFAULT_PING_TEMPLATE, DEFAULT_TEMPLATE_KEY, PingTemplateRepository

MAX_TEMPLATES_PER_GUILD = 5
SCRATCH_TEMPLATE_KEY = "desde-cero"
SCRATCH_PING_TEMPLATE = {
    "key": SCRATCH_TEMPLATE_KEY,
    "name": "Desde cero",
    "title": "",
    "title_editable": True,
    "mention": "",
    "join_command": "",
    "caller_slot": "",
    "roles": [],
    "slot_format": "",
    "content": "",
    "loot_link": "",
    "report_enabled": True,
    "scratch": True,
}


class PingTemplateService:
    def __init__(self):
        self.repo = PingTemplateRepository()

    def normalize_template(self, template):
        data = deepcopy(DEFAULT_PING_TEMPLATE)
        if isinstance(template, dict):
            data.update(template)

        roles = data.get("roles") or DEFAULT_PING_TEMPLATE["roles"]
        data["roles"] = [str(role).strip() for role in roles if str(role).strip()]
        if not data["roles"]:
            data["roles"] = list(DEFAULT_PING_TEMPLATE["roles"])

        caller_slot = str(data.get("caller_slot") or data["roles"][0]).strip()
        if caller_slot not in data["roles"]:
            data["roles"].insert(0, caller_slot)
        data["caller_slot"] = caller_slot

        data["key"] = str(data.get("key") or DEFAULT_TEMPLATE_KEY).lower()
        data["name"] = str(data.get("name") or data["key"])
        data["title"] = str(data.get("title") if data.get("title") is not None else DEFAULT_PING_TEMPLATE["title"])
        data["slot_format"] = str(data.get("slot_format") if data.get("slot_format") is not None else DEFAULT_PING_TEMPLATE["slot_format"])
        data["content"] = str(data.get("content") if data.get("content") is not None else DEFAULT_PING_TEMPLATE["content"])
        data["mention"] = str(data.get("mention") or "")
        data["join_command"] = str(data.get("join_command") if data.get("join_command") is not None else DEFAULT_PING_TEMPLATE["join_command"])
        data["loot_link"] = str(data.get("loot_link") or "")
        data["title_editable"] = bool(data.get("title_editable", True))
        data["report_enabled"] = bool(data.get("report_enabled", True))
        return data

    def normalize_key(self, value):
        key = re.sub(r"[^a-z0-9_-]+", "-", str(value or "").strip().lower())
        key = re.sub(r"-+", "-", key).strip("-_")
        return key[:32]

    def get_scratch_template(self):
        return deepcopy(SCRATCH_PING_TEMPLATE)

    def get_templates(self, guild_id, include_scratch=False):
        templates = {
            key: self.normalize_template({**template, "key": key})
            for key, template in self.repo.get_all(guild_id).items()
        }
        if include_scratch:
            templates = {SCRATCH_TEMPLATE_KEY: self.get_scratch_template(), **templates}

        return templates

    def get_saved_templates(self, guild_id):
        return {
            key: self.normalize_template({**template, "key": key})
            for key, template in self.repo.get_guild_templates(guild_id).items()
        }

    def get_template(self, guild_id, template_key):
        if str(template_key or "").lower() == SCRATCH_TEMPLATE_KEY:
            return self.get_scratch_template()

        return self.normalize_template(self.repo.get(guild_id, template_key))

    def get_default_template(self):
        return self.normalize_template(DEFAULT_PING_TEMPLATE)

    def can_add_template(self, guild_id):
        return self.repo.count_guild_templates(guild_id) < MAX_TEMPLATES_PER_GUILD

    def get_template_count(self, guild_id):
        return self.repo.count_guild_templates(guild_id)

    def add_template(self, guild_id, template_key, template):
        key = self.normalize_key(template_key)
        if not key:
            return None, "invalid"

        if key == SCRATCH_TEMPLATE_KEY:
            return None, "reserved"

        if self.repo.global_template_exists(key) or self.repo.guild_template_exists(guild_id, key):
            return None, "exists"

        if not self.can_add_template(guild_id):
            return None, "limit"

        data = self.normalize_template({**template, "key": key})
        self.repo.upsert(guild_id, key, data)
        return data, None

    def delete_template(self, guild_id, template_key):
        return self.repo.delete(guild_id, template_key)
