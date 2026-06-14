"""Config loading + merge.

Resolution order (lowest → highest precedence):
    1. vertical's vertical.yaml defaults
    2. the root harness.config.yaml (the user's fork-and-edit file)
    3. CLI flags (handled in cli.py)

Kept deliberately dependency-light: PyYAML is the only third-party import.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
PKG = Path(__file__).resolve().parent
VERTICALS_DIR = ROOT / "verticals"
CATALOG_PATH = PKG / "tools_catalog.yaml"


class ConfigError(Exception):
    """Raised when configuration is missing or invalid — surfaced cleanly in the CLI."""


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Missing file: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Expected a mapping at the top of {path}")
    return data


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay onto base. Lists are replaced, not concatenated."""
    out = dict(base)
    for key, val in overlay.items():
        if val is None or val == "":
            # Treat empty string / null as "not set" so blanks in the user's
            # config fall back to the vertical default instead of clobbering it.
            if key not in out:
                out[key] = val
            continue
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def expand(path_str: str) -> Path:
    """Expand ~ and env vars, returning an absolute Path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str))).resolve()


@dataclass
class HarnessConfig:
    raw: dict[str, Any]
    vertical_name: str
    vertical: dict[str, Any]
    root: Path = ROOT

    # ── convenience accessors ────────────────────────────────────────────────
    @property
    def business(self) -> dict:
        return self.raw.get("business", {})

    @property
    def tools_cfg(self) -> dict:
        return self.raw.get("tools", {})

    @property
    def brain_cfg(self) -> dict:
        return self.raw.get("brain", {})

    @property
    def rules_cfg(self) -> dict:
        return self.raw.get("rules", {})

    @property
    def memory_cfg(self) -> dict:
        return self.raw.get("memory", {})

    @property
    def out_dir(self) -> Path:
        out = self.raw.get("build", {}).get("out_dir", "./build")
        p = Path(out)
        return (self.root / p).resolve() if not p.is_absolute() else p

    @property
    def slug(self) -> str:
        name = self.business.get("name", "agent")
        agent_id = self.business.get("agent_id") or name
        return _slugify(agent_id)

    @property
    def persona_name(self) -> str:
        # Explicit override wins; else the vertical's recommended persona.
        return (
            self.rules_cfg.get("persona")
            or self.vertical.get("recommended", {}).get("persona")
            or "default"
        )

    @property
    def mnemo_path(self) -> Path:
        p = Path(self.memory_cfg.get("mnemo_cortex_path", "./mnemo-cortex"))
        return (self.root / p).resolve() if not p.is_absolute() else p


def _slugify(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "agent"


def list_verticals() -> list[dict[str, Any]]:
    """Discover every vertical (dir under verticals/ that has a vertical.yaml)."""
    out = []
    if not VERTICALS_DIR.exists():
        return out
    for child in sorted(VERTICALS_DIR.iterdir()):
        if child.name.startswith("_"):
            continue
        manifest = child / "vertical.yaml"
        if manifest.exists():
            data = _read_yaml(manifest)
            out.append(
                {
                    "name": child.name,
                    "title": data.get("title", child.name),
                    "description": data.get("description", ""),
                    "persona": data.get("recommended", {}).get("persona", "default"),
                    "profile": data.get("recommended", {}).get("tool_profile", "standard"),
                    "path": child,
                }
            )
    return out


def load_vertical(name: str) -> dict[str, Any]:
    """Load a vertical manifest, merged onto _base if present."""
    vdir = VERTICALS_DIR / name
    manifest = vdir / "vertical.yaml"
    if not manifest.exists():
        available = ", ".join(v["name"] for v in list_verticals()) or "(none)"
        raise ConfigError(
            f"Unknown vertical '{name}'. Available: {available}"
        )
    data = _read_yaml(manifest)
    base_dir = VERTICALS_DIR / "_base"
    if base_dir.exists() and name != "_base":
        base = _read_yaml(base_dir / "vertical.yaml")
        data = _deep_merge(base, data)
    data["_dir"] = str(vdir)
    return data


def load(config_path: Path | None = None) -> HarnessConfig:
    """Load the root config and its vertical."""
    cfg_path = config_path or (ROOT / "harness.config.yaml")
    raw = _read_yaml(cfg_path)
    vertical_name = raw.get("business", {}).get("vertical")
    if not vertical_name:
        raise ConfigError("business.vertical is required in harness.config.yaml")
    vertical = load_vertical(vertical_name)
    return HarnessConfig(raw=raw, vertical_name=vertical_name, vertical=vertical)


def load_catalog() -> dict[str, Any]:
    return _read_yaml(CATALOG_PATH)
