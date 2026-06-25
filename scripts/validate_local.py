import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SAFE_TEST_ARGS = [
    "-m",
    "unittest",
    "tests.test_settings",
    "tests.test_pagination",
    "tests.test_dashboard_action_repository",
    "tests.test_dashboard_action_service",
    "tests.test_permission_service",
    "tests.test_json_sqlite_migration",
    "tests.test_core_compatibility",
    "tests.test_dashboard_helpers",
    "tests.test_discord_metadata_service",
    "-v",
]


def run_step(name: str, args: list[str]) -> int:
    print(f"[validate] {name}", flush=True)
    result = subprocess.run([sys.executable, *args], cwd=ROOT_DIR)
    if result.returncode == 0:
        print(f"[validate] OK: {name}", flush=True)
    else:
        print(f"[validate] FAIL ({result.returncode}): {name}", flush=True)
    return result.returncode


def main() -> int:
    print("[validate] Baseline local seguro", flush=True)
    print("[validate] Este script no inicia el bot ni conecta a Discord.", flush=True)

    compile_rc = run_step("compileall", ["-m", "compileall", "."])
    safe_tests_rc = run_step("safe unittest suite", SAFE_TEST_ARGS)
    tests_rc = run_step("unittest discover", ["-m", "unittest", "discover", "-s", "tests", "-v"])
    pytest_rc = 0

    try:
        pytest_check = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            cwd=ROOT_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pytest_check = None

    if pytest_check and pytest_check.returncode == 0:
        pytest_rc = run_step("pytest", ["-m", "pytest"])
    else:
        print("[validate] SKIP: pytest no esta disponible en este entorno", flush=True)

    if compile_rc == 0 and safe_tests_rc == 0 and tests_rc == 0 and pytest_rc == 0:
        print("[validate] Resultado general: OK", flush=True)
        return 0

    print("[validate] Resultado general: con fallas", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
