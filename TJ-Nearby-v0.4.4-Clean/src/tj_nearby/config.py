from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .service import normalize_route_code


DEFAULT_CONFIG_PATH = Path("~/.tj-nearby/config.yaml").expanduser()


class ConfigError(ValueError):
    pass


def _deep_get(data: dict[str, Any], path: str, default: Any = None) -> Any:
    value: Any = data
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


@dataclass(slots=True)
class AppConfig:
    raw: dict[str, Any]
    path: Path

    def get(self, path: str, default: Any = None) -> Any:
        return _deep_get(self.raw, path, default)

    @property
    def state_dir(self) -> Path:
        path = Path("~/.tj-nearby").expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def gtfs_cache_path(self) -> Path:
        return Path(str(self.get("gtfs.cache_path", "~/.tj-nearby/gtfs.zip"))).expanduser()

    @property
    def legacy_preferred_routes(self) -> set[str]:
        """Return route codes stored by old releases in ``routes.preferred``.

        Releases before the desktop monitor used this list as a strict allowlist.
        That behaviour is surprising for a GPS-first nearby monitor because it can
        make the board look as if only one route exists. v0.4.2 therefore treats
        the old values as favorites unless the user explicitly enables the strict
        filter below.
        """
        values = self.get("routes.preferred", []) or []
        if isinstance(values, str):
            values = [values]
        return {normalize_route_code(value) for value in values if str(value).strip()}

    @property
    def preferred_routes(self) -> set[str]:
        """Optional strict route allowlist. Disabled by default in the GUI."""
        if not bool(self.get("routes.strict_filter_enabled", False)):
            return set()
        return self.legacy_preferred_routes

    @property
    def favorite_routes(self) -> set[str]:
        """Route favorites used for ranking, never physical bus-body favorites."""
        values = self.get("routes.favorites", None)
        if values is None:
            values = self.get("routes.favorite", []) or []
        if isinstance(values, str):
            values = [values]
        favorites = {normalize_route_code(value) for value in values if str(value).strip()}
        # Preserve the intent of old configs without hiding every other route.
        return favorites | self.legacy_preferred_routes


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise ConfigError(
            f"Config not found: {config_path}. Copy config.example.yaml to this path first."
        )
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("Config root must be a YAML mapping")
    return AppConfig(raw=data, path=config_path)


def save_config(config: AppConfig) -> None:
    """Persist the current configuration without discarding unknown keys."""
    config.path.parent.mkdir(parents=True, exist_ok=True)
    config.path.write_text(
        yaml.safe_dump(config.raw, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def set_config_value(config: AppConfig, path: str, value: Any) -> None:
    """Set a dotted YAML path and save it atomically enough for local use."""
    keys = path.split(".")
    target: dict[str, Any] = config.raw
    for key in keys[:-1]:
        child = target.get(key)
        if not isinstance(child, dict):
            child = {}
            target[key] = child
        target = child
    target[keys[-1]] = value
    save_config(config)
