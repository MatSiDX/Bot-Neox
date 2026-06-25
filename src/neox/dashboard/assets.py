from pathlib import Path


DASHBOARD_PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = DASHBOARD_PACKAGE_DIR / "templates"
STATIC_DIR = DASHBOARD_PACKAGE_DIR / "static"


def load_dashboard_template(name):
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def resolve_dashboard_static_path(relative_path):
    requested = str(relative_path or "").replace("\\", "/").lstrip("/")
    if not requested:
        return None

    root = STATIC_DIR.resolve()
    candidate = (root / requested).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    if not candidate.is_file():
        return None
    return candidate
