import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILES_LOADED = False


def load_env_files() -> None:
    """Load .env files once without overriding explicit process env vars."""
    global _ENV_FILES_LOADED
    if _ENV_FILES_LOADED:
        return
    _ENV_FILES_LOADED = True

    filenames = (".env",) if _is_pytest_process() else (".env", ".env.local")
    for filename in filenames:
        path = PROJECT_ROOT / filename
        if not path.exists():
            continue
        try:
            from dotenv import load_dotenv
        except ImportError:
            _load_env_file_fallback(path)
        else:
            load_dotenv(path, override=False)


def _load_env_file_fallback(path: Path) -> None:
    """Minimal dotenv parser used when python-dotenv is not installed yet."""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        os.environ[key] = value


def _is_pytest_process() -> bool:
    return "pytest" in sys.modules
