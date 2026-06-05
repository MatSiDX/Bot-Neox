import asyncio
from datetime import datetime
import re
from types import SimpleNamespace

import discord

from repositories.ping_template_repository import DEFAULT_PING_TEMPLATE
from services.config_service import CONFIG_REPORT_APPROVED_CHANNEL, CONFIG_REPORT_REVIEW_CHANNEL
from views.report_review_view import ReportReviewView

AVALONIAN_SLOTS = list(DEFAULT_PING_TEMPLATE["roles"])

SLOT_STYLES = {
    "OffTank": discord.ButtonStyle.secondary,
    "Cobra": discord.ButtonStyle.primary,
    "Heal": discord.ButtonStyle.success,
    "Falce supp": discord.ButtonStyle.danger,
    "SC": discord.ButtonStyle.primary,
    "Dps1": discord.ButtonStyle.danger,
    "Dps2": discord.ButtonStyle.danger,
    "DpsX": discord.ButtonStyle.danger,
    "Looter scout": discord.ButtonStyle.secondary,
}


class SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


class LeaveReasonModal(discord.ui.Modal, title="Justificacion de salida"):
    reason = discord.ui.TextInput(
        label="Indica por que te retiras",
        style=discord.TextStyle.paragraph,
        min_length=3,
        max_length=300,
    )

    def __init__(self, signup_view, user_id):
        super().__init__()
        self.signup_view = signup_view
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if self.signup_view.finalized:
            await interaction.response.send_message(
                "Este ping ya fue finalizado y ya no admite cambios.",
                ephemeral=True,
            )
            return

        slot_name = self.signup_view.remove_user(self.user_id)
        if not slot_name:
            await interaction.response.send_message("No estabas anotado en esta actividad.", ephemeral=True)
            return

        reason = str(self.reason.value)
        self.signup_view.log_interaction(interaction.user, "LEAVE", slot_name, reason)
        await self.signup_view.send_leave_log(interaction, slot_name, reason)
        await self.signup_view.refresh_message()
        await interaction.response.send_message(
            f"Te desanotaste de {slot_name}. Justificacion registrada.",
            ephemeral=True,
        )


class LeaveSignupView(discord.ui.View):
    def __init__(self, signup_view, user_id):
        super().__init__(timeout=None)
        self.signup_view = signup_view
        self.user_id = user_id

    @discord.ui.button(label="Desanotarse", style=discord.ButtonStyle.danger)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Este boton no es para ti.", ephemeral=True)
            return

        if self.signup_view.finalized:
            await interaction.response.send_message(
                "Este ping ya fue finalizado y ya no admite cambios.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(LeaveReasonModal(self.signup_view, self.user_id))


class ReportSubmissionModal(discord.ui.Modal, title="Enviar informe"):
    estimated = discord.ui.TextInput(label="Estimado", max_length=50)
    silver = discord.ui.TextInput(label="Silver", max_length=50)
    items = discord.ui.TextInput(label="Items", max_length=50)
    costs = discord.ui.TextInput(
        label="Mapa/Repa opcional",
        required=False,
        max_length=120,
        placeholder="Ej: mapa=1000000; repa=500000",
    )
    adjustments = discord.ui.TextInput(
        label="PP/Multas opcional",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
        placeholder="Ej: Heal:PP; Cobra:-50%",
    )

    def __init__(self, signup_view):
        super().__init__()
        self.signup_view = signup_view

    async def on_submit(self, interaction: discord.Interaction):
        await self.signup_view.submit_report(
            interaction,
            estimated=str(self.estimated.value),
            silver_text=str(self.silver.value),
            items_text=str(self.items.value),
            costs_text=str(self.costs.value or ""),
            adjustments_text=str(self.adjustments.value or ""),
        )


class AvalonSignupView(discord.ui.View):
    def __init__(
        self,
        *,
        numero_ava,
        join_command,
        caller,
        loot_link=None,
        guild_id=None,
        log_channel_id=0,
        avalonian_service=None,
        config_service=None,
        report_service=None,
        report_runtime_service=None,
        permission_service=None,
        balance_service=None,
        persist_callback=None,
        remove_persisted_callback=None,
        caller_id=None,
        caller_name=None,
        template=None,
        template_key=None,
        title=None,
        slots=None,
        finalized=False,
        report_sent=False,
        report_rejected=False,
        cancelled=False,
        cancelled_at=None,
        channel_id=0,
        message_id=0,
    ):
        super().__init__(timeout=None)
        self.template = self.normalize_template(template)
        self.template_key = template_key or self.template.get("key", "avalonianas")
        self.slot_names = list(self.template["roles"])
        self.slot_keys = self.build_slot_keys(self.slot_names)
        self.slot_labels = dict(zip(self.slot_keys, self.slot_names))
        configured_caller_slot = self.template["caller_slot"]
        caller_index = next(
            (
                index
                for index, slot_name in enumerate(self.slot_names)
                if self.slot_group_key(slot_name) == self.slot_group_key(configured_caller_slot)
            ),
            0,
        )
        self.caller_slot_key = self.slot_keys[caller_index]
        self.caller_slot = self.slot_labels[self.caller_slot_key]
        self.title = title or self.format_template_text(self.template["title"], numero=numero_ava)
        self.numero_ava = numero_ava
        self.join_command = join_command
        self.caller_name = caller_name or getattr(caller, "display_name", None) or getattr(caller, "name", None)
        self.loot_link = loot_link if loot_link is not None else self.template.get("loot_link")
        self.guild_id = guild_id
        self.log_channel_id = log_channel_id
        self.avalonian_service = avalonian_service
        self.config_service = config_service
        self.report_service = report_service
        self.report_runtime_service = report_runtime_service
        self.permission_service = permission_service
        self.balance_service = balance_service
        self.persist_callback = persist_callback
        self.remove_persisted_callback = remove_persisted_callback
        self.slots = {slot_key: None for slot_key in self.slot_keys}
        if slots:
            used_legacy_labels = set()
            for slot_key in self.slot_keys:
                slot_label = self.slot_labels[slot_key]
                if slot_key in slots:
                    self.slots[slot_key] = slots.get(slot_key)
                    continue

                if slot_label in slots and slot_label not in used_legacy_labels:
                    self.slots[slot_key] = slots.get(slot_label)
                    used_legacy_labels.add(slot_label)
        elif caller is not None:
            self.slots[self.caller_slot_key] = caller.id

        resolved_caller_id = caller.id if caller is not None else caller_id
        self.caller_id = resolved_caller_id or self.slots.get(self.caller_slot_key)
        self.message = None
        self.channel_id = channel_id
        self.message_id = message_id
        self.finalized = finalized
        self.report_sent = report_sent
        self.report_rejected = report_rejected
        self.cancelled = cancelled
        self.cancelled_at = cancelled_at
        self.delete_task = None
        self.rebuild_buttons()

    def slot_group_key(self, slot_name):
        return str(slot_name or "").strip().lower()

    def build_slot_keys(self, slot_names):
        keys = []
        counts = {}
        used = set()
        for index, slot_name in enumerate(slot_names, start=1):
            label = str(slot_name).strip()
            group_key = self.slot_group_key(label)
            counts[group_key] = counts.get(group_key, 0) + 1
            candidate = label if counts[group_key] == 1 else f"{label}#{counts[group_key]}"
            suffix = index
            while candidate in used:
                candidate = f"{label}#{suffix}"
                suffix += 1

            keys.append(candidate)
            used.add(candidate)

        return keys

    def get_slot_label(self, slot_key):
        return self.slot_labels.get(slot_key, slot_key)

    def iter_slots(self):
        for index, slot_key in enumerate(self.slot_keys, start=1):
            yield index, slot_key, self.get_slot_label(slot_key), self.slots.get(slot_key)

    def unique_slot_labels(self):
        labels = []
        seen = set()
        for slot_name in self.slot_names:
            group_key = self.slot_group_key(slot_name)
            if group_key in seen:
                continue

            labels.append(slot_name)
            seen.add(group_key)

        return labels

    def first_available_slot_key(self, slot_label):
        requested_group = self.slot_group_key(slot_label)
        for slot_key in self.slot_keys:
            if slot_key == self.caller_slot_key:
                continue
            if self.slot_group_key(self.get_slot_label(slot_key)) != requested_group:
                continue
            if self.slots.get(slot_key) is None:
                return slot_key

        return None

    def non_caller_slot_label_exists(self, slot_label):
        requested_group = self.slot_group_key(slot_label)
        return any(
            slot_key != self.caller_slot_key
            and self.slot_group_key(self.get_slot_label(slot_key)) == requested_group
            for slot_key in self.slot_keys
        )

    def available_slot_labels(self):
        labels = []
        seen = set()
        for slot_key in self.slot_keys:
            if slot_key == self.caller_slot_key or self.slots.get(slot_key) is not None:
                continue

            slot_label = self.get_slot_label(slot_key)
            group_key = self.slot_group_key(slot_label)
            if group_key in seen:
                continue

            labels.append(slot_label)
            seen.add(group_key)

        return labels

    def slot_mentions_for_label(self, slot_label):
        requested_group = self.slot_group_key(slot_label)
        mentions = []
        for _, slot_key, current_label, user_id in self.iter_slots():
            if self.slot_group_key(current_label) == requested_group and user_id:
                mentions.append(f"<@{user_id}>")

        return mentions

    def normalize_template(self, template):
        data = dict(DEFAULT_PING_TEMPLATE)
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
        data["key"] = str(data.get("key") or "avalonianas").lower()
        data["title"] = str(data.get("title") if data.get("title") is not None else DEFAULT_PING_TEMPLATE["title"])
        data["slot_format"] = str(data.get("slot_format") if data.get("slot_format") is not None else DEFAULT_PING_TEMPLATE["slot_format"])
        data["content"] = str(data.get("content") if data.get("content") is not None else DEFAULT_PING_TEMPLATE["content"])
        data["mention"] = str(data.get("mention") or "")
        data["join_command"] = str(data.get("join_command") if data.get("join_command") is not None else DEFAULT_PING_TEMPLATE["join_command"])
        data["loot_link"] = str(data.get("loot_link") or "")
        data["title_editable"] = bool(data.get("title_editable", True))
        data["report_enabled"] = bool(data.get("report_enabled", True))
        return data

    def format_template_text(self, text, **extra_values):
        values = SafeFormatDict(
            {
                "numero": self.numero_ava if hasattr(self, "numero_ava") else "",
                "title": getattr(self, "title", ""),
                "template": self.template.get("name", ""),
            }
        )
        values.update(extra_values)
        return str(text or "").format_map(values)

    @classmethod
    def from_state(cls, state, **kwargs):
        caller = SimpleNamespace(id=int(state["caller_id"]))
        return cls(
            numero_ava=int(state["numero_ava"]),
            join_command=state["join_command"],
            caller=caller,
            loot_link=state.get("loot_link"),
            guild_id=int(state["guild_id"]),
            log_channel_id=int(state.get("log_channel_id", 0)),
            caller_id=int(state["caller_id"]),
            caller_name=state.get("caller_name"),
            template=state.get("template"),
            template_key=state.get("template_key"),
            title=state.get("title"),
            slots=state.get("slots", {}),
            finalized=bool(state.get("finalized")),
            report_sent=bool(state.get("report_sent")),
            report_rejected=bool(state.get("report_rejected")),
            cancelled=bool(state.get("cancelled")),
            cancelled_at=state.get("cancelled_at"),
            channel_id=int(state.get("channel_id", 0)),
            message_id=int(state.get("message_id", 0)),
            **kwargs,
        )

    def to_state(self):
        return {
            "guild_id": self.guild_id,
            "caller_id": self.caller_id,
            "numero_ava": self.numero_ava,
            "template_key": self.template_key,
            "template": self.template,
            "title": self.title,
            "join_command": self.join_command,
            "caller_name": self.caller_name,
            "loot_link": self.loot_link,
            "log_channel_id": self.log_channel_id,
            "slots": self.slots,
            "finalized": self.finalized,
            "report_sent": self.report_sent,
            "report_rejected": self.report_rejected,
            "cancelled": self.cancelled,
            "cancelled_at": self.cancelled_at,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
        }

    def persist_state(self):
        if self.persist_callback:
            self.persist_callback(self.to_state())

    def remove_persisted_state(self, caller_id=None):
        if self.remove_persisted_callback:
            self.remove_persisted_callback(self.guild_id, caller_id or self.caller_id, self.numero_ava)

    def attach_message(self, message):
        self.message = message
        self.channel_id = getattr(message.channel, "id", 0)
        self.message_id = getattr(message, "id", 0)
        self.persist_state()

    def log_interaction(self, user, action, slot_name, reason=""):
        if not self.avalonian_service or not self.guild_id:
            return

        now = datetime.now()
        self.avalonian_service.log_interaction(
            self.guild_id,
            {
                "ava": self.numero_ava,
                "action": action,
                "user": user.display_name,
                "user_id": str(user.id),
                "slot": slot_name,
                "reason": reason,
                "date": now.strftime("%d/%m/%Y"),
                "time": now.strftime("%H:%M"),
            },
        )

    async def send_leave_log(self, interaction, slot_name, reason):
        if not self.log_channel_id:
            return

        channel = interaction.client.get_channel(self.log_channel_id)
        if channel is None:
            try:
                channel = await interaction.client.fetch_channel(self.log_channel_id)
            except discord.HTTPException:
                return

        try:
            await channel.send(
                f"**Retiro de {self.title}**\n"
                f"Usuario: {interaction.user.mention}\n"
                f"Cupo: {slot_name}\n"
                f"Motivo: {reason}"
            )
        except discord.HTTPException:
            return

    def find_user_slot_key(self, user_id):
        for slot_name, signed_user_id in self.slots.items():
            if signed_user_id == user_id:
                return slot_name
        return None

    def find_user_slot(self, user_id):
        slot_key = self.find_user_slot_key(user_id)
        return self.get_slot_label(slot_key) if slot_key else None

    def remove_user(self, user_id):
        slot_key = self.find_user_slot_key(user_id)
        if not slot_key or slot_key == self.caller_slot_key:
            return None

        slot_label = self.get_slot_label(slot_key)
        self.slots[slot_key] = None
        self.rebuild_buttons()
        self.persist_state()
        return slot_label

    def assign_user(self, slot_name, user):
        slot_key = self.first_available_slot_key(slot_name)
        if not slot_key:
            if self.non_caller_slot_label_exists(slot_name):
                return False, f"El cupo {slot_name} ya esta ocupado."
            if self.slot_group_key(slot_name) == self.slot_group_key(self.caller_slot):
                return False, f"{self.caller_slot} pertenece al caller del ping."
            return False, "Ese cupo no existe."

        slot_label = self.get_slot_label(slot_key)
        if slot_key == self.caller_slot_key:
            return False, f"{self.caller_slot} pertenece al caller del ping."

        current_slot = self.find_user_slot(user.id)
        if current_slot:
            return False, f"{user.mention} ya esta anotado como {current_slot}."

        self.slots[slot_key] = user.id
        self.log_interaction(user, "SIGNUP", slot_label)
        self.rebuild_buttons()
        self.persist_state()
        return True, f"{user.mention} fue anotado como {slot_label}."

    def remove_user_by_admin(self, user):
        slot_name = self.remove_user(user.id)
        if not slot_name:
            return None, f"{user.mention} no esta anotado en esta actividad."

        self.log_interaction(user, "LEAVE", slot_name, "Removido por caller")
        return slot_name, f"{user.mention} fue removido de {slot_name}."

    def fill_for_testing(self, user_ids):
        index = 0
        for slot_key in self.slot_keys:
            if slot_key == self.caller_slot_key:
                continue

            if index < len(user_ids):
                self.slots[slot_key] = user_ids[index]
                index += 1

        self.rebuild_buttons()
        self.persist_state()

    def occupied_count(self):
        return sum(1 for user_id in self.slots.values() if user_id)

    def is_full(self):
        return self.occupied_count() >= len(self.slot_keys)

    def is_caller(self, user_id):
        return user_id == self.caller_id

    def parse_amount(self, value):
        text = (value or "").strip().lower().replace(",", ".")
        suffix_match = re.search(r"([kmb]|mil|millon|millones|billo|billon|billones)\b", text)

        if suffix_match:
            amount_match = re.search(r"\d+(?:\.\d+)?", text)
            if not amount_match:
                return 0

            number = float(amount_match.group(0))
            suffix = suffix_match.group(1)
            multipliers = {
                "k": 1_000,
                "mil": 1_000,
                "m": 1_000_000,
                "millon": 1_000_000,
                "millones": 1_000_000,
                "b": 1_000_000_000,
                "billo": 1_000_000_000,
                "billon": 1_000_000_000,
                "billones": 1_000_000_000,
            }
            return int(number * multipliers.get(suffix, 1))

        digits = re.sub(r"\D", "", text)
        if not digits:
            return 0
        return int(digits)

    def parse_costs(self, value):
        text = (value or "").lower()
        mapa = 0
        repa = 0

        amount_pattern = r"(\d+(?:[\.,]\d+)*\s*(?:[kmb]|mil|millon|millones|billo|billon|billones)?)"
        mapa_match = re.search(rf"mapa\D*{amount_pattern}", text)
        repa_match = re.search(rf"repa\D*{amount_pattern}", text)
        if mapa_match:
            mapa = self.parse_amount(mapa_match.group(1))
        if repa_match:
            repa = self.parse_amount(repa_match.group(1))

        if not mapa_match and not repa_match:
            numbers = re.findall(amount_pattern, text)
            if numbers:
                mapa = self.parse_amount(numbers[0])
            if len(numbers) > 1:
                repa = self.parse_amount(numbers[1])

        return mapa, repa

    def parse_adjustments(self, value):
        adjustments = {}
        if not value:
            return adjustments

        slot_lookup = {self.slot_group_key(slot): slot for slot in self.unique_slot_labels()}
        parts = re.split(r"[;\n,]+", value)
        for raw_part in parts:
            if ":" not in raw_part:
                continue

            raw_slot, raw_note = raw_part.split(":", 1)
            slot_name = slot_lookup.get(self.slot_group_key(raw_slot))
            note = raw_note.strip()
            if slot_name and note:
                adjustments[slot_name] = note

        return adjustments

    def format_amount(self, amount):
        amount = int(amount)
        abs_amount = abs(amount)
        sign = "-" if amount < 0 else ""
        units = [
            (1_000_000_000, "B"),
            (1_000_000, "M"),
            (1_000, "K"),
        ]

        for value, suffix in units:
            if abs_amount >= value:
                number = abs_amount / value
                formatted = f"{number:.2f}".rstrip("0").rstrip(".")
                return f"{sign}{formatted}{suffix}"

        return f"{sign}{abs_amount}"

    def format_full_amount(self, amount):
        return f"{int(amount):,}".replace(",", ".")

    def parse_percentage_discount(self, note):
        match = re.search(r"-(\d+(?:\.\d+)?)\s*%", note or "", flags=re.IGNORECASE)
        if not match:
            return 0.0
        return float(match.group(1))

    def is_pp_note(self, note):
        return "pp" in (note or "").lower()

    def build_report_distribution(self, per_user, adjustments):
        distribution = []
        for index, _, slot_name, user_id in self.iter_slots():
            if not user_id:
                continue

            note = adjustments.get(slot_name, "")
            discount = self.parse_percentage_discount(note)
            payout = int(per_user * max(0.0, (100.0 - discount)) / 100.0)
            category = "silver" if self.is_pp_note(note) else "items"

            distribution.append(
                {
                    "index": index,
                    "slot": slot_name,
                    "user_id": user_id,
                    "note": note,
                    "category": category,
                    "amount": payout,
                }
            )

        return distribution

    def evaluate_pp_distribution(self, silver, mapa, repa, distribution):
        pp_entries = [entry for entry in distribution if entry["category"] == "silver"]
        available_silver = max(silver - mapa - repa, 0)
        pp_required = sum(entry["amount"] for entry in pp_entries)
        difference = available_silver - pp_required
        return pp_entries, available_silver, pp_required, difference

    def build_pp_evaluation_block(self, silver, mapa, repa, distribution):
        pp_entries, available_silver, pp_required, difference = self.evaluate_pp_distribution(
            silver,
            mapa,
            repa,
            distribution,
        )
        if not pp_entries:
            return ""

        lines = [
            "",
            "## Revision PP",
            f"**PP:** {len(pp_entries)}",
            f"**Silver total:** {self.format_amount(available_silver)}",
            f"**Silver requerido para PP:** {self.format_amount(pp_required)}",
        ]

        if difference > 0:
            lines.append(f"**Silver sobrante:** {self.format_amount(difference)}")
        elif difference < 0:
            lines.append(f"**Silver faltante:** {self.format_amount(abs(difference))}")
        else:
            lines.append("**Silver exacto para PP:** 0")

        return "\n".join(lines)

    def build_report_content(self, estimated, silver, items, mapa, repa, adjustments):
        total = silver + items - mapa - repa
        total = max(total, 0)
        participant_count = self.occupied_count()
        per_user = total // participant_count if participant_count else 0
        estimated_amount = self.parse_amount(estimated)
        estimated_value = self.format_amount(estimated_amount) if estimated_amount else estimated

        lines = [
            f"# {self.title}",
            "",
            f"**Estimado:** {estimated_value}",
            f"**Silver:** {self.format_amount(silver)}",
            f"**Items:** {self.format_amount(items)}",
        ]

        if mapa:
            lines.append(f"**Mapa:** {self.format_amount(-mapa)}")
        if repa:
            lines.append(f"**Repa:** {self.format_amount(-repa)}")

        lines.extend([
            f"**Total:** {self.format_amount(total)}",
            "",
            f"# {self.format_full_amount(per_user)} C/U",
            "",
        ])

        for index, _, slot_name, user_id in self.iter_slots():
            value = f"<@{user_id}>" if user_id else ""
            note = adjustments.get(slot_name, "")
            suffix = f" {note}" if note else ""
            lines.append(f"> {index}.{slot_name}: {value}{suffix}")

        return "\n".join(lines)

    async def get_configured_channel(self, interaction, channel_type):
        if not self.config_service:
            return None

        channel_id = self.config_service.get_channel_id(interaction.guild.id, channel_type)
        if not channel_id:
            return None

        channel = interaction.client.get_channel(channel_id)
        if channel:
            return channel

        try:
            return await interaction.client.fetch_channel(channel_id)
        except discord.HTTPException:
            return None

    async def create_report_thread(self, message):
        try:
            await message.create_thread(name=f"Evaluacion {self.title}")
        except discord.HTTPException:
            return

    async def mark_report_rejected(self):
        self.report_sent = False
        self.report_rejected = True
        self.rebuild_buttons()
        self.persist_state()
        await self.refresh_message()

    async def delete_cancelled_message_later(self):
        remaining_seconds = 600
        if self.cancelled_at:
            try:
                cancelled_time = datetime.fromisoformat(self.cancelled_at)
                elapsed = (datetime.now() - cancelled_time).total_seconds()
                remaining_seconds = max(0, 600 - int(elapsed))
            except ValueError:
                remaining_seconds = 600

        await asyncio.sleep(remaining_seconds)
        if not self.message:
            return

        try:
            await self.message.delete()
            self.remove_persisted_state()
        except discord.HTTPException:
            return

    async def submit_report(self, interaction, *, estimated, silver_text, items_text, costs_text, adjustments_text):
        if not self.is_caller(interaction.user.id):
            await interaction.response.send_message("Solo el caller puede enviar este informe.", ephemeral=True)
            return

        if not self.finalized:
            await interaction.response.send_message("Primero debes finalizar el ping.", ephemeral=True)
            return

        if self.report_sent:
            await interaction.response.send_message("Este informe ya fue enviado a evaluacion.", ephemeral=True)
            return

        review_channel = await self.get_configured_channel(interaction, CONFIG_REPORT_REVIEW_CHANNEL)
        approved_channel_id = self.config_service.get_channel_id(
            interaction.guild.id,
            CONFIG_REPORT_APPROVED_CHANNEL,
        ) if self.config_service else 0

        if not review_channel:
            await interaction.response.send_message(
                "No hay canal de evaluacion de informes configurado. Usa /config canal.",
                ephemeral=True,
            )
            return

        silver = self.parse_amount(silver_text)
        items = self.parse_amount(items_text)
        mapa, repa = self.parse_costs(costs_text)
        adjustments = self.parse_adjustments(adjustments_text)
        content = self.build_report_content(estimated, silver, items, mapa, repa, adjustments)
        total = max(silver + items - mapa - repa, 0)
        participant_count = self.occupied_count()
        per_user = total // participant_count if participant_count else 0
        distribution = self.build_report_distribution(per_user, adjustments)
        _, available_silver, pp_required, pp_difference = self.evaluate_pp_distribution(
            silver,
            mapa,
            repa,
            distribution,
        )
        if pp_difference < 0:
            await interaction.response.send_message(
                "El informe no es valido: el silver disponible no alcanza para cubrir los PP indicados.",
                ephemeral=True,
            )
            return

        evaluation_content = (
            "## Informe en evaluacion\n\n"
            f"{content}"
            f"{self.build_pp_evaluation_block(silver, mapa, repa, distribution)}"
        )

        report_data = {
            "ava": self.numero_ava,
            "caller": interaction.user.display_name,
            "caller_id": interaction.user.id,
            "content": content,
            "evaluation_content": evaluation_content,
            "per_user": per_user,
            "distribution": distribution,
            "available_silver": available_silver,
            "pp_required": pp_required,
        }
        review_view = ReportReviewView(
            report_data=report_data,
            approved_channel_id=approved_channel_id,
            report_service=self.report_service,
            permission_service=self.permission_service,
            balance_service=self.balance_service,
            source_view=self,
            runtime_service=getattr(self, "report_runtime_service", None),
            guild_id=interaction.guild.id,
        )
        message = await review_channel.send(
            evaluation_content,
            view=review_view,
        )
        review_view.message = message
        review_view.message_id = message.id
        if getattr(self, "report_runtime_service", None):
            self.report_runtime_service.save_review(
                {
                    "guild_id": interaction.guild.id,
                    "channel_id": review_channel.id,
                    "message_id": message.id,
                    "approved_channel_id": approved_channel_id,
                    "report_data": report_data,
                }
            )
        await self.create_report_thread(message)

        self.report_sent = True
        self.report_rejected = False
        self.rebuild_buttons()
        self.persist_state()
        await self.refresh_message()
        await interaction.response.send_message("Informe enviado a evaluacion.", ephemeral=True)

    def transfer_caller(self, new_caller, join_command):
        previous_caller_id = self.caller_id
        previous_slot_key = self.find_user_slot_key(new_caller.id)
        previous_slot = self.get_slot_label(previous_slot_key) if previous_slot_key else None

        if previous_caller_id == new_caller.id:
            return False, "Ese usuario ya es el caller de esta actividad."

        if previous_slot_key and previous_slot_key != self.caller_slot_key:
            self.slots[previous_slot_key] = None

        self.slots[self.caller_slot_key] = new_caller.id
        self.caller_id = new_caller.id
        self.caller_name = getattr(new_caller, "display_name", None) or getattr(new_caller, "name", None)
        self.join_command = join_command
        self.rebuild_buttons()
        self.persist_state()

        if previous_caller_id:
            self.log_transfer(previous_caller_id, new_caller, previous_slot)

        return True, previous_slot

    def log_transfer(self, previous_caller_id, new_caller, released_slot):
        if not self.avalonian_service or not self.guild_id:
            return

        now = datetime.now()
        reason = "Transferencia de caller"
        if released_slot:
            reason = f"Transferencia de caller; libero {released_slot}"

        self.avalonian_service.log_interaction(
            self.guild_id,
            {
                "ava": self.numero_ava,
                "action": "LEAVE",
                "user": f"Usuario {previous_caller_id}",
                "user_id": str(previous_caller_id),
                "slot": self.caller_slot,
                "reason": reason,
                "date": now.strftime("%d/%m/%Y"),
                "time": now.strftime("%H:%M"),
            },
        )
        self.avalonian_service.log_interaction(
            self.guild_id,
            {
                "ava": self.numero_ava,
                "action": "SIGNUP",
                "user": new_caller.display_name,
                "user_id": str(new_caller.id),
                "slot": self.caller_slot,
                "reason": reason,
                "date": now.strftime("%d/%m/%Y"),
                "time": now.strftime("%H:%M"),
            },
        )

    def build_slot_lines(self):
        slot_lines = []
        slot_format = str(self.template.get("slot_format") or "").strip() or "{slot}: {user}"
        for index, _, slot_name, user_id in self.iter_slots():
            user_value = f"<@{user_id}>" if user_id else ""
            slot_lines.append(
                self.format_template_text(
                    slot_format,
                    index=index,
                    slot=slot_name,
                    user=user_value,
                )
            )

        return slot_lines

    def line_matches_slot(self, line, slot_name):
        pattern = rf"(?<!\w){re.escape(slot_name)}(?!\w)"
        return re.search(pattern, line, flags=re.IGNORECASE) is not None

    def inject_slot_users(self, content):
        lines = str(content or "").splitlines()
        used_slot_groups = set()
        rendered_lines = []

        for line in lines:
            rendered_line = line
            for slot_name in self.unique_slot_labels():
                group_key = self.slot_group_key(slot_name)
                if group_key in used_slot_groups or not self.line_matches_slot(line, slot_name):
                    continue

                user_value = " ".join(self.slot_mentions_for_label(slot_name))
                if "{user}" in rendered_line:
                    rendered_line = rendered_line.replace("{user}", user_value)
                elif user_value and "<@" not in rendered_line:
                    rendered_line = f"{rendered_line} {user_value}".rstrip()

                used_slot_groups.add(group_key)
                break

            rendered_lines.append(rendered_line.replace("{user}", ""))

        return "\n".join(rendered_lines)

    def build_content(self):
        taken = sum(1 for user_id in self.slots.values() if user_id)
        status = ""
        if self.cancelled:
            status = "\n\n**Estado:** Cancelada"

        rendered_content = self.format_template_text(
            self.template.get("content", DEFAULT_PING_TEMPLATE["content"]),
            mention=self.template.get("mention", ""),
            join_command=self.join_command,
            caller=self.caller_name or f"Usuario {self.caller_id}",
            slots="\n".join(self.build_slot_lines()),
            loot_link=self.loot_link or "",
            occupied=taken,
            total=len(self.slot_keys),
            status=status,
        )
        return self.inject_slot_users(rendered_content)

    def rebuild_buttons(self):
        self.clear_items()

        free_slots = self.available_slot_labels()

        if not self.cancelled and not self.finalized:
            for index, slot_name in enumerate(free_slots[:20]):
                button = discord.ui.Button(
                    label=slot_name,
                    style=SLOT_STYLES.get(slot_name, discord.ButtonStyle.primary),
                    custom_id=f"avalonian:{self.guild_id}:{self.caller_id}:{self.numero_ava}:{slot_name}",
                    row=index // 5,
                )
                button.callback = self.create_signup_callback(slot_name)
                self.add_item(button)

            cancel_button = discord.ui.Button(
                label="Cancelar ping",
                style=discord.ButtonStyle.danger,
                custom_id=f"avalonian:cancel:{self.guild_id}:{self.caller_id}:{self.numero_ava}",
                row=4,
            )
            cancel_button.callback = self.cancel_ping_callback
            self.add_item(cancel_button)

            finish_button = discord.ui.Button(
                label="Finalizar ping",
                style=discord.ButtonStyle.success,
                custom_id=f"avalonian:finish:{self.guild_id}:{self.caller_id}:{self.numero_ava}",
                row=4,
            )
            finish_button.callback = self.finish_ping_callback
            self.add_item(finish_button)

        if self.finalized and not self.cancelled and self.template.get("report_enabled", True):
            report_label = "Reenviar informe" if self.report_rejected and not self.report_sent else "Enviar informe"
            report_button = discord.ui.Button(
                label=report_label,
                style=discord.ButtonStyle.primary,
                custom_id=f"avalonian:report:{self.guild_id}:{self.caller_id}:{self.numero_ava}",
                row=4,
                disabled=not self.finalized or self.report_sent,
            )
            report_button.callback = self.send_report_callback
            self.add_item(report_button)

    async def cancel_ping_callback(self, interaction: discord.Interaction):
        if not self.is_caller(interaction.user.id):
            await interaction.response.send_message("Solo el caller puede cancelar esta Ava.", ephemeral=True)
            return

        if self.report_sent:
            await interaction.response.send_message(
                "No puedes cancelar una Ava que ya envio informe.",
                ephemeral=True,
            )
            return

        self.cancelled = True
        self.cancelled_at = datetime.now().isoformat()
        self.rebuild_buttons()
        self.persist_state()
        await interaction.response.edit_message(content=self.build_content(), view=None)
        if self.delete_task is None or self.delete_task.done():
            self.delete_task = asyncio.create_task(self.delete_cancelled_message_later())
        await interaction.followup.send(
            "Ava cancelada. Ya puedes volver a usar ese numero. El anuncio se eliminara automaticamente en 10 minutos.",
            ephemeral=True,
        )

    async def finish_ping_callback(self, interaction: discord.Interaction):
        if not self.is_caller(interaction.user.id):
            await interaction.response.send_message("Solo el caller puede finalizar este ping.", ephemeral=True)
            return

        if self.cancelled:
            await interaction.response.send_message("Esta Ava ya fue cancelada.", ephemeral=True)
            return

        if self.finalized:
            await interaction.response.send_message("Este ping ya fue finalizado.", ephemeral=True)
            return

        self.finalized = True
        self.rebuild_buttons()
        self.persist_state()
        await interaction.response.edit_message(content=self.build_content(), view=self)
        await interaction.followup.send(
            "Ping finalizado. Ahora puedes enviar el informe con base en las personas anotadas.",
            ephemeral=True,
        )

    async def send_report_callback(self, interaction: discord.Interaction):
        if not self.is_caller(interaction.user.id):
            await interaction.response.send_message("Solo el caller puede enviar este informe.", ephemeral=True)
            return

        if self.cancelled:
            await interaction.response.send_message("Esta Ava fue cancelada y ya no puede enviar informe.", ephemeral=True)
            return

        if not self.finalized:
            await interaction.response.send_message("Primero debes finalizar el ping.", ephemeral=True)
            return

        if self.report_sent:
            await interaction.response.send_message("Este informe ya fue enviado a evaluacion.", ephemeral=True)
            return

        await interaction.response.send_modal(ReportSubmissionModal(self))

    def create_signup_callback(self, slot_name):
        async def callback(interaction: discord.Interaction):
            if self.cancelled:
                await interaction.response.send_message("Esta Ava fue cancelada.", ephemeral=True)
                return

            if self.finalized:
                await interaction.response.send_message(
                    "Este ping ya fue finalizado y no admite nuevas inscripciones.",
                    ephemeral=True,
                )
                return

            current_slot_key = self.find_user_slot_key(interaction.user.id)
            if current_slot_key:
                current_slot = self.get_slot_label(current_slot_key)
                if current_slot_key == self.caller_slot_key:
                    await interaction.response.send_message(
                        "Usted se va a desanotar de la actividad. Para eso usted tiene que dejar a otro caller a cargo de esta actividad. Usa /ping-transfer member para transferir el ping.",
                        ephemeral=True,
                    )
                    return

                await interaction.response.send_message(
                    f"Ya estas anotado como {current_slot}.",
                    view=LeaveSignupView(self, interaction.user.id),
                    ephemeral=True,
                )
                return

            slot_key = self.first_available_slot_key(slot_name)
            if not slot_key:
                self.rebuild_buttons()
                await self.refresh_message()
                await interaction.response.send_message("Ese cupo ya fue tomado.", ephemeral=True)
                return

            slot_label = self.get_slot_label(slot_key)
            self.slots[slot_key] = interaction.user.id
            self.log_interaction(interaction.user, "SIGNUP", slot_label)
            self.rebuild_buttons()
            self.persist_state()
            await interaction.response.edit_message(content=self.build_content(), view=self)
            await interaction.followup.send(
                f"Te anotaste como {slot_label}.",
                view=LeaveSignupView(self, interaction.user.id),
                ephemeral=True,
            )

        return callback

    async def refresh_message(self):
        if self.message:
            view = None if self.cancelled else self
            await self.message.edit(content=self.build_content(), view=view)
