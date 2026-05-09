from pathlib import Path

BASE_DIR_PATH = Path(__file__).parent
APP_DIR_PATH = BASE_DIR_PATH / "app"
TEMPLATES_DIR_PATH = APP_DIR_PATH / "templates"
COMPONENTS_DIR_PATH = TEMPLATES_DIR_PATH / "components"
STATIC_DIR_PATH = APP_DIR_PATH / "static"
