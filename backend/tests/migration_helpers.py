"""Run Alembic against disposable SQLite databases in a subprocess."""
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic(db_path: Path, *args: str) -> None:
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db_path}")
    result = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=str(BACKEND_DIR),
                            capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
