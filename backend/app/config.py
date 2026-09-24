import ipaddress
import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError

# Absolute path for the DB in the project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "swing_trading.db"

_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def validate_origin(origin: object) -> str:
    """Return a browser origin (scheme://host[:port]) or raise ValueError.

    Rejects '*', 'null', empty values, wildcards, paths (including a trailing
    slash), queries, credentials, non-HTTP(S) schemes and malformed hosts/ports.
    """
    if not isinstance(origin, str) or not origin or origin != origin.strip():
        raise ValueError("origin must be a non-empty string without spaces")
    if "*" in origin or origin.lower() == "null":
        raise ValueError(f"wildcard or null origin is not allowed: {origin!r}")
    try:
        parts = urlsplit(origin)
        port = parts.port
    except ValueError:
        raise ValueError(f"malformed origin: {origin!r}") from None
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"origin must use http or https: {origin!r}")
    if parts.path or parts.query or parts.fragment or parts.username or parts.password:
        raise ValueError(f"origin must be scheme://host[:port] with no path or trailing slash: {origin!r}")
    host = parts.hostname or ""
    if host.startswith("[") or ":" in host:
        try:
            ipaddress.IPv6Address(host.strip("[]"))
        except ValueError:
            raise ValueError(f"malformed host in origin: {origin!r}") from None
        host_part = f"[{host.strip('[]')}]"
    elif re.fullmatch(r"[0-9.]+", host):
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            raise ValueError(f"malformed host in origin: {origin!r}") from None
        host_part = host
    elif host and all(_DNS_LABEL.fullmatch(label) for label in host.split(".")):
        host_part = host
    else:
        raise ValueError(f"malformed host in origin: {origin!r}")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError(f"malformed port in origin: {origin!r}")
    canonical = f"{parts.scheme}://{host_part}" + (f":{port}" if port is not None else "")
    if origin != canonical:
        raise ValueError(f"origin must be lowercase scheme://host[:port]: {origin!r}")
    return origin


class Settings(BaseSettings):
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    # Browser origins allowed to call the API directly (the Vite dev server).
    # Override with a JSON list in CORS_ALLOWED_ORIGINS if Vite runs elsewhere.
    cors_allowed_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env")

    @field_validator("cors_allowed_origins")
    @classmethod
    def _check_origins(cls, origins: list[str]) -> list[str]:
        return [validate_origin(o) for o in origins]


def _load_settings() -> Settings:
    """Fail closed with one concise line instead of starting with a bad configuration."""
    try:
        return Settings()
    except ValidationError as exc:
        err = exc.errors()[0]
        field = str(err["loc"][0]).upper() if err.get("loc") else "setting"
        raise SystemExit(f"Invalid configuration for {field}: {err['msg'].removeprefix('Value error, ')}") from None
    except SettingsError:
        raise SystemExit("Invalid configuration: CORS_ALLOWED_ORIGINS must be a JSON list of origins, "
                         'for example ["http://127.0.0.1:5173"]') from None


settings = _load_settings()
