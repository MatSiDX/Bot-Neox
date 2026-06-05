import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from repositories.database import DATABASE_FILE, init_database


def main():
    init_database()

    backup_dir = PROJECT_ROOT / "data" / "backups" / "sqlite"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"

    source = sqlite3.connect(DATABASE_FILE)
    try:
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()

    print(f"Backup creado: {backup_path}")


if __name__ == "__main__":
    main()
