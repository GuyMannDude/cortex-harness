"""The tool loader.

Turns (profile + enable + disable) into a concrete, validated set of tools, and
reports which ones were dropped and why. The compiler uses the result to write
the MCP config and the TOOLS brain lane so the agent only ever sees what the
business turned on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import HarnessConfig, load_catalog


@dataclass
class ResolvedTools:
    enabled: list[str]
    dropped: dict[str, str]          # tool -> reason it was dropped
    warnings: list[str] = field(default_factory=list)
    catalog: dict[str, Any] = field(default_factory=dict)

    def by_group(self) -> dict[str, list[str]]:
        tools = self.catalog.get("tools", {})
        grouped: dict[str, list[str]] = {}
        for name in self.enabled:
            grp = tools.get(name, {}).get("group", "other")
            grouped.setdefault(grp, []).append(name)
        return grouped


def _active_features(cfg: HarnessConfig) -> set[str]:
    """Which optional capabilities are available in this deployment.

    Used to validate a tool's `requires:` list. A tool whose prerequisite is
    missing is dropped (with a reason) rather than silently exposed and failing
    at runtime.
    """
    feats: set[str] = set()
    # brain_dir always exists — the compiler writes one for every build.
    feats.add("brain_dir")
    isolation = cfg.memory_cfg.get("isolation", "isolated")
    if isolation in ("shared", "hybrid"):
        feats.add("shared_store")
    if cfg.memory_cfg.get("bus", {}).get("enabled"):
        feats.add("bus")
    return feats


def resolve(cfg: HarnessConfig) -> ResolvedTools:
    catalog = load_catalog()
    all_tools: dict[str, Any] = catalog.get("tools", {})
    profiles: dict[str, Any] = catalog.get("profiles", {})

    profile_name = cfg.tools_cfg.get("profile") or cfg.vertical.get(
        "recommended", {}
    ).get("tool_profile", "standard")
    if profile_name not in profiles:
        raise ValueError(
            f"Unknown tool profile '{profile_name}'. "
            f"Choose one of: {', '.join(profiles)}"
        )

    # Expand the profile ("*" means every catalogued tool).
    profile_tools = profiles[profile_name].get("tools", [])
    if profile_tools == ["*"]:
        selected = set(all_tools)
    else:
        selected = set(profile_tools)

    warnings: list[str] = []

    # Layer the vertical's own recommended additions, then the user's.
    vertical_enable = cfg.vertical.get("recommended", {}).get("enable", []) or []
    for name in list(vertical_enable) + list(cfg.tools_cfg.get("enable", []) or []):
        if name not in all_tools:
            warnings.append(f"enable: unknown tool '{name}' ignored")
            continue
        selected.add(name)

    for name in cfg.tools_cfg.get("disable", []) or []:
        if name not in all_tools:
            warnings.append(f"disable: unknown tool '{name}' ignored")
        selected.discard(name)

    # Validate prerequisites.
    feats = _active_features(cfg)
    enabled: list[str] = []
    dropped: dict[str, str] = {}
    for name in sorted(selected):
        reqs = all_tools[name].get("requires", []) or []
        missing = [r for r in reqs if r not in feats]
        if missing:
            dropped[name] = f"requires {', '.join(missing)} (not configured)"
        else:
            enabled.append(name)

    return ResolvedTools(
        enabled=enabled, dropped=dropped, warnings=warnings, catalog=catalog
    )
