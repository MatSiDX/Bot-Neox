import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from repositories.database import DATABASE_FILE, get_connection
from services.balance_service import BalanceService


def main():
    BalanceService()

    with get_connection() as connection:
        balances = connection.execute("SELECT COUNT(*) FROM economy_balances").fetchone()[0]
        operations = connection.execute("SELECT COUNT(*) FROM economy_operations").fetchone()[0]

    print("Migracion SQLite completada")
    print(f"Base de datos: {DATABASE_FILE}")
    print(f"Balances: {balances}")
    print(f"Operaciones: {operations}")


if __name__ == "__main__":
    main()
