import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def read_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")


def backup_file(path, backup_dir):
    if path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)


def is_guild_balance(data):
    return isinstance(data, dict) and all(isinstance(value, dict) for value in data.values())


def normalize_balance(user_balance):
    return {
        "items": int(user_balance.get("items", 0)),
        "silver": int(user_balance.get("silver", 0)),
    }


def import_balances(current_path, incoming_path):
    current = read_json(current_path)
    incoming = read_json(incoming_path)

    stats = {
        "guilds_added": 0,
        "users_added": 0,
        "users_preserved": 0,
        "invalid_entries_skipped": 0,
    }

    for guild_id, users in incoming.items():
        if not is_guild_balance(users):
            stats["invalid_entries_skipped"] += 1
            continue

        if guild_id not in current:
            current[guild_id] = {}
            stats["guilds_added"] += 1

        for user_id, balance in users.items():
            if user_id in current[guild_id]:
                stats["users_preserved"] += 1
                continue

            current[guild_id][user_id] = normalize_balance(balance)
            stats["users_added"] += 1

    write_json(current_path, current)
    return stats


def convert_history_entry(entry, balances_by_guild, guild_id):
    user_id = str(entry.get("user_id", ""))
    raw_timestamp = str(entry.get("timestamp", ""))
    date = ""
    time = ""

    if raw_timestamp:
        parts = raw_timestamp.split()
        date = parts[0] if parts else ""
        time = parts[1][:5] if len(parts) > 1 else ""

    action_type = str(entry.get("action", "")).upper()
    category = str(entry.get("type", "")).lower()
    player_balance = balances_by_guild.get(str(guild_id), {}).get(user_id, {})

    return {
        "action": "/add" if action_type == "ADD" else "/remove",
        "operator": "Importado",
        "operator_id": "",
        "player": player_balance.get("name", f"Usuario {user_id}"),
        "player_id": user_id,
        "type": action_type,
        "category": "Items" if category == "items" else "Silver",
        "amount": int(entry.get("amount", 0)),
        "previous_balance": "",
        "new_balance": "",
        "date": date,
        "time": time,
    }


def import_history(current_path, incoming_history_path, incoming_balances_path):
    current = read_json(current_path)
    incoming = read_json(incoming_history_path)
    incoming_balances = read_json(incoming_balances_path)

    imported = 0
    for guild_id, entries in incoming.items():
        if not isinstance(entries, list):
            continue

        if guild_id not in current:
            current[guild_id] = []

        existing_keys = {
            (
                operation.get("player_id"),
                operation.get("type"),
                operation.get("category"),
                operation.get("amount"),
                operation.get("date"),
                operation.get("time"),
            )
            for operation in current[guild_id]
        }

        for entry in entries:
            operation = convert_history_entry(entry, incoming_balances, guild_id)
            key = (
                operation.get("player_id"),
                operation.get("type"),
                operation.get("category"),
                operation.get("amount"),
                operation.get("date"),
                operation.get("time"),
            )
            if key in existing_keys:
                continue

            current[guild_id].append(operation)
            existing_keys.add(key)
            imported += 1

    write_json(current_path, current)
    return imported


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=".tmp_import_data/data")
    parser.add_argument("--target", default="data")
    args = parser.parse_args()

    source = Path(args.source)
    target = Path(args.target)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = target / "backups" / f"import_{timestamp}"

    target_balances = target / "balances.json"
    target_operations = target / "operations.json"
    incoming_balances = source / "balances.json"
    incoming_history = source / "history.json"

    backup_file(target_balances, backup_dir)
    backup_file(target_operations, backup_dir)

    balance_stats = import_balances(target_balances, incoming_balances)
    operations_imported = import_history(target_operations, incoming_history, incoming_balances)

    from repositories.balance_repository import BalanceRepository
    from repositories.operation_repository import OperationRepository

    BalanceRepository().replace_all(read_json(target_balances))
    OperationRepository().replace_all(read_json(target_operations))

    print("Import completed")
    print(f"Backup: {backup_dir}")
    print(f"Guilds added: {balance_stats['guilds_added']}")
    print(f"Users added: {balance_stats['users_added']}")
    print(f"Existing users preserved: {balance_stats['users_preserved']}")
    print(f"Invalid entries skipped: {balance_stats['invalid_entries_skipped']}")
    print(f"Operations imported: {operations_imported}")
    print("SQLite updated: data/bot.sqlite3")


if __name__ == "__main__":
    main()
