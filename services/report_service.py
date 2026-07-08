from repositories.report_repository import ReportRepository

REPORT_SPLIT_ITEMS = "items"
REPORT_SPLIT_SILVER = "silver"
REPORT_SPLIT_BOTH = "items_silver"
REPORT_SPLIT_LABELS = {
    REPORT_SPLIT_ITEMS: "Solo items",
    REPORT_SPLIT_SILVER: "Solo silver",
    REPORT_SPLIT_BOTH: "Items + silver",
}


class ReportService:
    def __init__(self):
        self.repo = ReportRepository()

    def log_generation(self, guild_id, report):
        self.repo.append(guild_id, report)

    def log_review(self, guild_id, report):
        self.repo.append(guild_id, report)

    def get_reviews(self, guild_id):
        return self.repo.get_by_guild(guild_id)


class ReportFormatService:
    def parse_amount(self, value):
        import re

        text = str(value or "").strip().lower().replace(" ", "")
        if not text:
            return 0

        suffix_match = re.fullmatch(
            r"(\d+(?:[\.,]\d+)?)(k|m|b|mil|millon|millones|billo|billon|billones)",
            text,
        )
        if suffix_match:
            number = float(suffix_match.group(1).replace(",", "."))
            suffix = suffix_match.group(2)
            multiplier = {
                "k": 1_000,
                "mil": 1_000,
                "m": 1_000_000,
                "millon": 1_000_000,
                "millones": 1_000_000,
                "b": 1_000_000_000,
                "billo": 1_000_000_000,
                "billon": 1_000_000_000,
                "billones": 1_000_000_000,
            }[suffix]
            return int(number * multiplier)

        digits = re.sub(r"\D", "", text)
        if not digits:
            return 0
        return int(digits)

    def parse_costs(self, value):
        import re

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

    def parse_percentage(self, value):
        import re

        match = re.search(r"\d+(?:[\.,]\d+)?", str(value or ""))
        if not match:
            return 0.0
        return max(0.0, min(float(match.group(0).replace(",", ".")), 100.0))

    def parse_adjustments(self, value, slot_labels):
        import re

        adjustments = {}
        if not value:
            return adjustments

        slot_lookup = {self.slot_group_key(slot): slot for slot in slot_labels}
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

    def slot_group_key(self, value):
        import re

        text = re.sub(r"#\d+$", "", str(value or "").strip().lower())
        return re.sub(r"\s+", " ", text)

    def normalize_fines(self, fines, occupied_user_ids, find_user_slot):
        normalized = []
        valid_user_ids = {int(user_id) for user_id in occupied_user_ids if user_id}
        for entry in fines or []:
            if not isinstance(entry, dict):
                continue
            user_id = int(entry.get("user_id") or 0)
            amount = self.parse_amount(entry.get("amount"))
            reason = str(entry.get("reason") or "").strip()
            if not user_id or user_id not in valid_user_ids or amount <= 0 or not reason:
                continue
            normalized.append(
                {
                    "user_id": user_id,
                    "user_name": str(entry.get("user_name") or f"Usuario {user_id}"),
                    "slot": str(entry.get("slot") or find_user_slot(user_id) or ""),
                    "amount": amount,
                    "reason": reason[:300],
                    "proof_path": str(entry.get("proof_path") or ""),
                    "proof_name": str(entry.get("proof_name") or ""),
                }
            )
        return normalized

    def normalize_split_exclusions(self, exclusions, slots):
        slot_by_user_id = {
            int(slot.get("user_id") or 0): slot
            for slot in slots or []
            if slot.get("user_id")
        }
        normalized = []
        seen_user_ids = set()
        for entry in exclusions or []:
            if not isinstance(entry, dict):
                continue
            try:
                user_id = int(entry.get("user_id") or 0)
            except (TypeError, ValueError):
                continue
            if not user_id or user_id in seen_user_ids or user_id not in slot_by_user_id:
                continue

            slot = slot_by_user_id[user_id]
            reason = str(entry.get("reason") or "").strip()
            raw_activity_percentage = str(entry.get("activity_percentage") or "").strip()
            activity_percentage = (
                self.parse_percentage(raw_activity_percentage)
                if raw_activity_percentage
                else 100.0
            )
            user_name = str(
                entry.get("user_name")
                or entry.get("display_name")
                or slot.get("mention")
                or f"Usuario {user_id}"
            ).strip()
            normalized.append(
                {
                    "user_id": user_id,
                    "user_name": user_name[:120],
                    "slot": str(slot.get("slot") or entry.get("slot") or "")[:80],
                    "reason": reason[:300],
                    "activity_percentage": activity_percentage,
                }
            )
            seen_user_ids.add(user_id)
        return normalized

    def normalize_split_modifiers(self, modifiers, slots):
        import re

        slot_by_user_id = {
            int(slot.get("user_id") or 0): slot
            for slot in slots or []
            if slot.get("user_id")
        }
        normalized = []
        seen = set()
        for entry in modifiers or []:
            if not isinstance(entry, dict):
                continue

            name = str(entry.get("name") or entry.get("concept") or "").strip()
            operation = str(entry.get("operation") or "").strip().lower()
            target_type = str(entry.get("target_type") or "total").strip().lower()
            description = str(entry.get("description") or "").strip()
            if operation in {"sum", "plus", "add", "+", "suma"}:
                operation = "add"
            elif operation in {"subtract", "minus", "remove", "-", "resta"}:
                operation = "subtract"
            else:
                continue

            amount_text = str(entry.get("amount") or "").strip()
            amount = self.parse_amount(amount_text)
            if not name or not re.search(r"\d", amount_text) or amount_text.startswith("-") or amount < 0:
                continue

            user_id = 0
            user_name = ""
            slot_name = ""
            if target_type == "player":
                try:
                    user_id = int(entry.get("user_id") or 0)
                except (TypeError, ValueError):
                    continue
                slot = slot_by_user_id.get(user_id)
                if not slot:
                    continue
                user_name = str(
                    entry.get("user_name")
                    or entry.get("display_name")
                    or slot.get("mention")
                    or f"Usuario {user_id}"
                ).strip()
                slot_name = str(slot.get("slot") or entry.get("slot") or "").strip()
            else:
                target_type = "total"

            dedupe_key = (
                self.slot_group_key(name),
                operation,
                amount,
                target_type,
                user_id,
                self.slot_group_key(description),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized.append(
                {
                    "name": name[:120],
                    "operation": operation,
                    "amount": amount,
                    "description": description[:300],
                    "target_type": target_type,
                    "user_id": user_id,
                    "user_name": user_name[:120],
                    "slot": slot_name[:80],
                }
            )
        return normalized

    def normalize_build_loan_discounts(self, discounts, slots):
        slot_by_user_id = {
            int(slot.get("user_id") or 0): slot
            for slot in slots or []
            if slot.get("user_id")
        }
        normalized = []
        seen = set()
        for entry in discounts or []:
            if not isinstance(entry, dict):
                continue
            try:
                user_id = int(entry.get("user_id") or entry.get("player_id") or 0)
            except (TypeError, ValueError):
                continue
            slot = slot_by_user_id.get(user_id)
            amount_text = str(entry.get("amount") or "").strip()
            amount = self.parse_amount(amount_text)
            reason = str(
                entry.get("reason")
                or entry.get("description")
                or entry.get("motivo")
                or ""
            ).strip()
            collection_method = str(
                entry.get("collection_method")
                or entry.get("method")
                or entry.get("metodo_cobro")
                or "split"
            ).strip().lower()
            if collection_method in {
                "split",
                "from_split",
                "discount_from_split",
                "descuento_desde_split",
                "descuento desde split",
                "descontar del split",
            }:
                collection_method = "split"
            elif collection_method in {
                "balance",
                "from_balance",
                "discount_from_balance",
                "descuento_desde_balance",
                "descuento desde balance",
                "descontar del balance",
            }:
                collection_method = "balance"
            elif collection_method in {
                "paid_now",
                "pay_now",
                "instant_payment",
                "pago_al_momento",
                "pago al momento",
            }:
                collection_method = "paid_now"
            else:
                continue
            if not slot or not reason:
                continue
            if collection_method != "paid_now" and amount <= 0:
                continue

            dedupe_key = (user_id, amount, self.slot_group_key(reason), collection_method)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            user_name = str(
                entry.get("user_name")
                or entry.get("player")
                or entry.get("display_name")
                or slot.get("mention")
                or f"Usuario {user_id}"
            ).strip()
            normalized.append(
                {
                    "user_id": user_id,
                    "user_name": user_name[:120],
                    "slot": str(slot.get("slot") or entry.get("slot") or "")[:80],
                    "amount": amount,
                    "reason": reason[:300],
                    "collection_method": collection_method,
                    "proof_path": str(entry.get("proof_path") or ""),
                    "proof_name": str(entry.get("proof_name") or "")[:120],
                }
            )
        return normalized

    def split_modifier_signed_amount(self, modifier):
        amount = int(modifier.get("amount") or 0)
        return amount if modifier.get("operation") == "add" else -amount

    def split_modifier_label(self, modifier):
        operation_label = "+" if modifier.get("operation") == "add" else "-"
        return f"{operation_label}{self.format_full_amount(modifier.get('amount') or 0)} {modifier.get('name') or 'Ajuste'}"

    def split_global_modifier_total(self, modifiers):
        return sum(
            self.split_modifier_signed_amount(modifier)
            for modifier in modifiers or []
            if modifier.get("target_type") == "total"
        )

    def split_exclusion_discount(self, exclusion):
        if not isinstance(exclusion, dict):
            return 0.0
        return max(0.0, min(float(exclusion.get("activity_percentage") or 0), 100.0))

    def split_exclusion_multiplier(self, exclusion):
        return max(0.0, (100.0 - self.split_exclusion_discount(exclusion)) / 100.0)

    def split_participant_weight(self, user_id, exclusions):
        if not user_id:
            return 0.0
        for exclusion in exclusions or []:
            if int(exclusion.get("user_id") or 0) == int(user_id):
                return self.split_exclusion_multiplier(exclusion)
        return 1.0

    def split_participant_count(self, user_ids, exclusions):
        return sum(
            self.split_participant_weight(user_id, exclusions)
            for user_id in user_ids
            if user_id
        )

    def parse_percentage_discount(self, note):
        import re

        match = re.search(r"-(\d+(?:\.\d+)?)\s*%", note or "", flags=re.IGNORECASE)
        if not match:
            return 0.0
        return float(match.group(1))

    def is_pp_note(self, note):
        return "pp" in (note or "").lower()

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

    def calculate_split(
        self,
        silver,
        items,
        mapa,
        repa,
        participant_count,
        split_mode,
        caller_percentage=0.0,
        looter_payment=0,
        looter_user_id=0,
        tab_sale_percentage=0.0,
        split_modifiers=None,
    ):
        split_mode = split_mode if split_mode in REPORT_SPLIT_LABELS else REPORT_SPLIT_ITEMS
        net_items = max(int(items or 0), 0)
        raw_silver = max(int(silver or 0), 0)
        caller_percentage = max(0.0, min(float(caller_percentage or 0), 100.0)) if split_mode == REPORT_SPLIT_BOTH else 0.0
        looter_payment = max(int(looter_payment or 0), 0) if split_mode == REPORT_SPLIT_BOTH else 0
        looter_user_id = int(looter_user_id or 0) if split_mode == REPORT_SPLIT_BOTH else 0
        tab_sale_percentage = max(0.0, min(float(tab_sale_percentage or 0), 100.0)) if split_mode in {REPORT_SPLIT_ITEMS, REPORT_SPLIT_BOTH} else 0.0
        caller_amount = int(raw_silver * (caller_percentage / 100.0)) if caller_percentage else 0
        net_silver = max(raw_silver - caller_amount - looter_payment - int(mapa or 0) - int(repa or 0), 0)
        tab_sale_active = split_mode in {REPORT_SPLIT_ITEMS, REPORT_SPLIT_BOTH} and tab_sale_percentage > 0
        sold_tab_value = int(net_items * ((100.0 - tab_sale_percentage) / 100.0)) if tab_sale_active else 0
        effective_mode = split_mode
        split_participants = max(float(participant_count or 0) - (1 if looter_payment and looter_user_id else 0), 0.0)

        if split_mode == REPORT_SPLIT_ITEMS:
            item_base = sold_tab_value if tab_sale_active else net_items
            item_pool = max(item_base + raw_silver - int(mapa or 0) - int(repa or 0), 0)
            silver_pool = 0
        elif split_mode == REPORT_SPLIT_SILVER:
            item_pool = 0
            silver_pool = net_items + net_silver
        elif tab_sale_active:
            item_pool = 0
            silver_pool = max(net_silver - caller_amount, 0) + sold_tab_value
            effective_mode = REPORT_SPLIT_SILVER
        else:
            item_pool = net_items
            silver_pool = net_silver

        global_modifier_total = self.split_global_modifier_total(split_modifiers)
        if global_modifier_total:
            if effective_mode == REPORT_SPLIT_ITEMS:
                item_pool = max(item_pool + global_modifier_total, 0)
            else:
                silver_pool = max(silver_pool + global_modifier_total, 0)

        return {
            "mode": effective_mode,
            "label": REPORT_SPLIT_LABELS[effective_mode],
            "requested_mode": split_mode,
            "item_pool": item_pool,
            "silver_pool": silver_pool,
            "item_per_user": int(item_pool // split_participants) if split_participants else 0,
            "silver_per_user": int(silver_pool // split_participants) if split_participants else 0,
            "total": item_pool + silver_pool,
            "net_silver": net_silver,
            "caller_percentage": caller_percentage,
            "caller_amount": caller_amount,
            "looter_payment": looter_payment,
            "looter_user_id": looter_user_id,
            "tab_sale_percentage": tab_sale_percentage,
            "tab_sale_active": tab_sale_active,
            "sold_tab_value": sold_tab_value,
            "global_modifier_total": global_modifier_total,
            "split_participants": split_participants,
        }

    def build_distribution(self, slots, caller_id, split, adjustments, exclusions=None, split_modifiers=None, build_loan_discounts=None):
        distribution = []
        exclusion_by_user_id = {
            int(exclusion.get("user_id") or 0): exclusion
            for exclusion in exclusions or []
            if isinstance(exclusion, dict)
        }
        player_modifiers_by_user_id = {}
        for modifier in split_modifiers or []:
            if modifier.get("target_type") != "player":
                continue
            user_id = int(modifier.get("user_id") or 0)
            if user_id:
                player_modifiers_by_user_id.setdefault(user_id, []).append(modifier)
        build_loan_discounts_by_user_id = {}
        for discount in build_loan_discounts or []:
            user_id = int(discount.get("user_id") or 0)
            if user_id:
                build_loan_discounts_by_user_id.setdefault(user_id, []).append(discount)

        for slot in slots:
            index = slot.get("index")
            slot_name = slot.get("slot")
            user_id = int(slot.get("user_id") or 0)
            if not user_id:
                continue
            exclusion_multiplier = self.split_exclusion_multiplier(exclusion_by_user_id.get(user_id))
            if exclusion_multiplier <= 0:
                continue

            if split.get("looter_payment") and int(split.get("looter_user_id", 0) or 0) == user_id:
                distribution.append(
                    {
                        "index": index,
                        "slot": slot_name,
                        "user_id": user_id,
                        "note": "Looter",
                        "category": "silver",
                        "amount": int(split["looter_payment"]),
                        "is_pp": False,
                    }
                )
                if int(split.get("caller_amount", 0) or 0) and user_id == int(caller_id or 0):
                    distribution.append(
                        {
                            "index": index,
                            "slot": slot_name,
                            "user_id": user_id,
                            "note": "Caller",
                            "category": "silver",
                            "amount": int(split["caller_amount"]),
                            "is_pp": False,
                        }
                    )
                continue

            note = adjustments.get(slot_name, "")
            discount = self.parse_percentage_discount(note)
            multiplier = max(0.0, (100.0 - discount)) / 100.0
            categories = []
            if split["item_per_user"]:
                categories.append(("items", split["item_per_user"]))
            if split["silver_per_user"]:
                categories.append(("silver", split["silver_per_user"]))

            if split["mode"] == REPORT_SPLIT_ITEMS and self.is_pp_note(note):
                categories = [("silver", split["item_per_user"])]

            for category, base_amount in categories:
                distribution.append(
                    {
                        "index": index,
                        "slot": slot_name,
                        "user_id": user_id,
                        "note": note,
                        "category": category,
                        "amount": int(base_amount * multiplier * exclusion_multiplier),
                        "is_pp": self.is_pp_note(note),
                    }
                )

            if int(split.get("caller_amount", 0) or 0) and user_id == int(caller_id or 0):
                distribution.append(
                    {
                        "index": index,
                        "slot": slot_name,
                        "user_id": user_id,
                        "note": "Caller",
                        "category": "silver",
                        "amount": int(split["caller_amount"]),
                        "is_pp": False,
                    }
                )

            for modifier in player_modifiers_by_user_id.get(user_id, []):
                signed_amount = self.split_modifier_signed_amount(modifier)
                if not signed_amount:
                    continue
                distribution.append(
                    {
                        "index": index,
                        "slot": slot_name,
                        "user_id": user_id,
                        "note": self.split_modifier_label(modifier),
                        "category": "silver",
                        "amount": signed_amount,
                        "is_pp": False,
                        "modifier": True,
                    }
                )

            for discount in build_loan_discounts_by_user_id.get(user_id, []):
                collection_method = str(discount.get("collection_method") or "split")
                if collection_method not in {"split", "balance"}:
                    continue
                amount = int(discount.get("amount") or 0)
                if amount <= 0:
                    continue
                reason = str(discount.get("reason") or "Préstamo de build").strip()
                if collection_method == "balance":
                    reason = f"descontado del balance: {reason}"
                distribution.append(
                    {
                        "index": index,
                        "slot": slot_name,
                        "user_id": user_id,
                        "note": f"Préstamo de build: {reason}",
                        "category": "silver",
                        "amount": -amount,
                        "is_pp": False,
                        "build_loan_discount": True,
                        "collection_method": collection_method,
                    }
                )

        return distribution

    def build_player_suffix(self, slot_name, user_id, caller_id, adjustments, split, exclusions=None, split_modifiers=None, build_loan_discounts=None):
        if not user_id:
            return ""

        parts = []
        exclusion = next(
            (
                exclusion
                for exclusion in exclusions or []
                if int(exclusion.get("user_id") or 0) == int(user_id)
            ),
            None,
        )
        if exclusion:
            reason = str(exclusion.get("reason") or "").strip()
            activity_percentage = self.split_exclusion_discount(exclusion)
            label = "Excluido del split" if activity_percentage >= 100 else "Descuento de actividad"
            parts.append(f"{label}: {reason}" if reason else label)
            if activity_percentage < 100:
                parts.append(f"-{activity_percentage:g}%")
            return f" {' '.join(parts)}"

        note = adjustments.get(slot_name, "")
        is_looter = (
            split.get("looter_payment")
            and int(split.get("looter_user_id", 0) or 0) == int(user_id)
        )
        if note and not (is_looter and note.strip().lower() == "looter"):
            parts.append(note)

        if is_looter:
            parts.append("Looter")
            parts.append(f"+{self.format_full_amount(split['looter_payment'])}")

        if int(split.get("caller_amount", 0) or 0) and int(user_id) == int(caller_id or 0):
            parts.append(f"+ {self.format_full_amount(split['caller_amount'])}")

        for modifier in split_modifiers or []:
            if modifier.get("target_type") == "player" and int(modifier.get("user_id") or 0) == int(user_id):
                parts.append(self.split_modifier_label(modifier))

        for discount in build_loan_discounts or []:
            if int(discount.get("user_id") or 0) == int(user_id):
                if str(discount.get("collection_method") or "split") != "split":
                    continue
                parts.append(f"-{self.format_full_amount(discount.get('amount') or 0)} préstamo de build")

        return f" {' '.join(parts)}" if parts else ""

    def evaluate_pp_distribution(self, split, distribution):
        pp_entries = [
            entry
            for entry in distribution
            if entry.get("is_pp") and entry["category"] == "silver"
        ]
        if split["mode"] == REPORT_SPLIT_ITEMS:
            available_silver = int(split.get("net_silver", 0) or 0)
        else:
            available_silver = int(split.get("silver_pool", 0) or 0)
        pp_required = sum(entry["amount"] for entry in pp_entries)
        difference = available_silver - pp_required
        return pp_entries, available_silver, pp_required, difference

    def build_pp_evaluation_block(self, split, distribution):
        pp_entries, available_silver, pp_required, difference = self.evaluate_pp_distribution(split, distribution)
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

    def build_fines_block(self, fines):
        if not fines:
            return ""
        lines = [
            "",
            "## Multas propuestas",
        ]
        for fine in fines:
            lines.append(
                f"- <@{fine['user_id']}> | {fine.get('slot') or 'Sin cupo'} | {self.format_full_amount(fine['amount'])} | {fine['reason']}"
            )
        return "\n".join(lines)

    def build_exclusions_block(self, exclusions):
        if not exclusions:
            return ""
        lines = [
            "",
            "## Excluidos del split",
        ]
        for exclusion in exclusions:
            reason = str(exclusion.get("reason") or "").strip()
            activity_percentage = self.split_exclusion_discount(exclusion)
            label = "Excluido del split" if activity_percentage >= 100 else "Descuento de actividad"
            detail = f" | {reason}" if reason else ""
            percentage_detail = f" | -{activity_percentage:g}%" if activity_percentage < 100 else ""
            lines.append(
                f"- <@{exclusion['user_id']}> | {exclusion.get('slot') or 'Sin cupo'} | {label}{detail}{percentage_detail}"
            )
        return "\n".join(lines)

    def build_modifiers_block(self, modifiers):
        if not modifiers:
            return ""
        lines = [
            "",
            "## Modificadores del split",
        ]
        for modifier in modifiers:
            target = "Total general"
            if modifier.get("target_type") == "player":
                target = f"<@{modifier['user_id']}> | {modifier.get('slot') or 'Sin cupo'}"
            description = str(modifier.get("description") or "").strip()
            detail = f" | {description}" if description else ""
            lines.append(
                f"- {modifier.get('name') or 'Ajuste'} | {target} | {self.split_modifier_label(modifier)}{detail}"
            )
        return "\n".join(lines)

    def build_build_loan_discounts_block(self, discounts):
        if not discounts:
            return ""
        lines = [
            "",
            "## Préstamos de build",
        ]
        method_labels = {
            "split": "se le resta del split",
            "balance": "se le descontara del balance",
            "paid_now": "pago al momento",
        }
        for discount in discounts:
            reason = str(discount.get("reason") or "Préstamo de build").strip()
            method = str(discount.get("collection_method") or "split")
            method_label = method_labels.get(method, method_labels["split"])
            if method == "paid_now" and int(discount.get("amount") or 0) <= 0:
                lines.append(
                    f"- <@{discount['user_id']}> | {method_label}: {reason}"
                )
                continue
            lines.append(
                f"- <@{discount['user_id']}> | {self.format_full_amount(discount['amount'])} | {method_label}: {reason}"
            )
        return "\n".join(lines)

    def build_report_content(self, *, title, caller_id, estimated, silver, items, mapa, repa, adjustments, split, slots, exclusions=None, split_modifiers=None, build_loan_discounts=None):
        estimated_amount = int(estimated or 0) if isinstance(estimated, int) else 0
        estimated_value = self.format_amount(estimated_amount) if estimated_amount else str(estimated or "")

        lines = [
            f"# {title}",
            "",
            f"**Modo de reparto:** {split['label']}",
            f"**Estimado:** {estimated_value}",
            f"**Silver:** {self.format_amount(silver)}",
            f"**Items:** {self.format_amount(items)}",
        ]

        if mapa:
            lines.append(f"**Mapa:** {self.format_amount(-mapa)}")
        if repa:
            lines.append(f"**Repa:** {self.format_amount(-repa)}")
        if split.get("tab_sale_active"):
            lines.append(f"**Venta de tab:** -{float(split.get('tab_sale_percentage') or 0):g}%")
        if int(split.get("global_modifier_total", 0) or 0):
            lines.append(f"**Modificadores:** {self.format_amount(split['global_modifier_total'])}")

        lines.extend([
            f"**Total neto:** {self.format_amount(split['total'])}",
            "",
        ])
        if split["item_per_user"]:
            lines.append(f"# {self.format_full_amount(split['item_per_user'])} Items C/U")
        if split["silver_per_user"]:
            lines.append(f"# {self.format_full_amount(split['silver_per_user'])} Silver C/U")
        lines.append("")

        for slot in slots:
            user_id = slot.get("user_id")
            if "mention" in slot:
                value = str(slot.get("mention") or "")
            else:
                value = f"<@{user_id}>" if user_id else ""
            suffix = self.build_player_suffix(slot.get("slot"), user_id, caller_id, adjustments, split, exclusions, split_modifiers, build_loan_discounts)
            lines.append(f"> {slot.get('index')}.{slot.get('slot')}: {value}{suffix}")

        modifiers_block = self.build_modifiers_block(split_modifiers)
        if modifiers_block:
            lines.append(modifiers_block)
        build_loan_discounts_block = self.build_build_loan_discounts_block(build_loan_discounts)
        if build_loan_discounts_block:
            lines.append(build_loan_discounts_block)
        exclusions_block = self.build_exclusions_block(exclusions)
        if exclusions_block:
            lines.append(exclusions_block)
        return "\n".join(lines)

    def build_final_report_text(self, *, content, fines, split, distribution, build_loan_discounts=None):
        return (
            "## Informe en evaluacion\n\n"
            f"{content}"
            f"{self.build_fines_block(fines)}"
            f"{self.build_pp_evaluation_block(split, distribution)}"
        )
