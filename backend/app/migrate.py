"""Run Alembic migrations from code (API startup and seed.py)."""
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["configure_logger"] = False  # keep the app's logging setup
    return cfg


def upgrade_db() -> None:
    command.upgrade(alembic_config(), "head")
