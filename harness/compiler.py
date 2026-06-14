"""The compiler.

Takes a HarnessConfig + resolved tools and writes a self-contained, runnable
workspace under build/<slug>/:

    build/<slug>/
      brain/                 rendered brain lanes (identity, rules, tools, playbooks)
      agentb.yaml            Mnemo Cortex backend config (carries the persona rule-set)
      mcp.json               MCP client config — registers the bridge with enabled tools
      TOOLS.md               human-readable summary of what was turned on
      start.sh / start.ps1   one command to launch the memory backend + print next steps
      manifest.json          machine-readable record of the build

Template syntax is intentionally tiny: {{ key.path }} placeholders resolved
against a flat context. No Jinja dependency.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import HarnessConfig, expand
from .loader import ResolvedTools

_PLACEHOLDER = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def _flatten(prefix: str, obj: Any, out: dict[str, str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(f"{prefix}.{k}" if prefix else k, v, out)
    elif isinstance(obj, (list, tuple)):
        out[prefix] = ", ".join(str(x) for x in obj)
    else:
        out[prefix] = "" if obj is None else str(obj)


def _render(text: str, context: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        return context.get(key, m.group(0))  # leave unknown placeholders visible

    return _PLACEHOLDER.sub(sub, text)


def _build_context(cfg: HarnessConfig) -> dict[str, str]:
    ctx: dict[str, str] = {}
    _flatten("business", cfg.business, ctx)
    _flatten("vars", cfg.brain_cfg.get("vars", {}), ctx)
    _flatten("vertical", {"name": cfg.vertical_name,
                          "title": cfg.vertical.get("title", cfg.vertical_name)}, ctx)
    ctx["persona"] = cfg.persona_name
    ctx["agent_id"] = cfg.business.get("agent_id", cfg.slug)
    # Friendly bare aliases for the most common placeholders.
    ctx.setdefault("name", cfg.business.get("name", "the business"))
    ctx.setdefault("tagline", cfg.business.get("tagline", ""))
    return ctx


@dataclass
class BuildResult:
    out_dir: Path
    brain_dir: Path
    files: list[Path]


# ── persona / rule-set ───────────────────────────────────────────────────────

# Built-in persona presets mirror Mnemo Cortex's config.py defaults so a build
# is self-contained even if the vertical doesn't define a custom persona.
_BUILTIN_PERSONAS: dict[str, dict] = {
    "default": {"preflight": "balanced", "context_bias": "neutral",
                "max_confidence_for_pass": 0.7, "allow_speculative": False},
    "strict": {"preflight": "aggressive", "context_bias": "factual",
               "max_confidence_for_pass": 0.9, "allow_speculative": False,
               "l1_similarity_override": 0.8, "l2_similarity_override": 0.6},
    "creative": {"preflight": "permissive", "context_bias": "associative",
                 "max_confidence_for_pass": 0.5, "allow_speculative": True,
                 "l1_similarity_override": 0.6, "l2_similarity_override": 0.35},
}


def _resolve_persona(cfg: HarnessConfig) -> dict:
    name = cfg.persona_name
    # Start from a vertical-defined persona, else a builtin, else default.
    vertical_personas = cfg.vertical.get("personas", {}) or {}
    base = dict(vertical_personas.get(name) or _BUILTIN_PERSONAS.get(name)
                or _BUILTIN_PERSONAS["default"])
    base.update(cfg.rules_cfg.get("overrides", {}) or {})
    base["name"] = name
    return base


# ── emitters ─────────────────────────────────────────────────────────────────

def _emit_brain(cfg: HarnessConfig, tools: ResolvedTools, brain_dir: Path,
                context: dict[str, str]) -> list[Path]:
    written: list[Path] = []
    src_brain = Path(cfg.vertical["_dir"]) / "brain"
    base_brain = cfg.root / "verticals" / "_base" / "brain"

    # Copy base brain files first, then let the vertical override by filename.
    seen: dict[str, Path] = {}
    for srcdir in (base_brain, src_brain):
        if srcdir.exists():
            for f in sorted(srcdir.glob("*.md")):
                seen[f.name] = f

    for fname, srcfile in seen.items():
        rendered = _render(srcfile.read_text(encoding="utf-8"), context)
        dest = brain_dir / fname
        dest.write_text(rendered, encoding="utf-8")
        written.append(dest)

    # Always (re)generate the rules + tools lanes from live config so they can
    # never drift from what was actually compiled.
    written.append(_emit_rules_lane(cfg, brain_dir, context))
    written.append(_emit_tools_lane(cfg, tools, brain_dir))
    return written


def _emit_rules_lane(cfg: HarnessConfig, brain_dir: Path,
                     context: dict[str, str]) -> Path:
    persona = _resolve_persona(cfg)
    rules_md = Path(cfg.vertical["_dir"]) / "rules.md"
    body = _render(rules_md.read_text(encoding="utf-8"), context) if rules_md.exists() else ""
    speculative = "ALLOWED" if persona.get("allow_speculative") else "NOT allowed"
    lane = f"""# OPERATING RULES — {context.get('name', '')}

> Auto-generated from the **{persona['name']}** persona + this vertical's rules.
> Edit `verticals/{cfg.vertical_name}/rules.md` or the persona, then rebuild.

## Posture
- **Preflight rigor:** {persona.get('preflight', 'balanced')}
- **Context bias:** {persona.get('context_bias', 'neutral')}
- **Confidence required to assert without flagging:** {persona.get('max_confidence_for_pass', 0.7)}
- **Speculation:** {speculative}

## Rule set
{body}
"""
    dest = brain_dir / "rules.md"
    dest.write_text(lane, encoding="utf-8")
    return dest


def _emit_tools_lane(cfg: HarnessConfig, tools: ResolvedTools, brain_dir: Path) -> Path:
    catalog_tools = tools.catalog.get("tools", {})
    groups = tools.catalog.get("groups", {})
    lines = [
        "# ENABLED TOOLS",
        "",
        "> Auto-generated by the tool loader. These are the ONLY memory-layer "
        "tools turned on for this agent. Use them as described.",
        "",
    ]
    for group, names in sorted(tools.by_group().items()):
        lines.append(f"## {group} — {groups.get(group, '')}")
        for name in names:
            meta = catalog_tools.get(name, {})
            lines.append(f"- **`{name}`** — {meta.get('summary', '')}")
            if meta.get("when"):
                lines.append(f"  - _When:_ {meta['when']}")
        lines.append("")
    if tools.dropped:
        lines.append("## Disabled / unavailable")
        for name, reason in sorted(tools.dropped.items()):
            lines.append(f"- `{name}` — {reason}")
        lines.append("")
    dest = brain_dir / "tools.md"
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def _emit_agentb_yaml(cfg: HarnessConfig, out_dir: Path) -> Path:
    persona = _resolve_persona(cfg)
    data_dir = str(expand(cfg.memory_cfg.get("data_dir", "~/.cortex-harness")))
    doc = {
        "data_dir": data_dir,
        "log_level": "info",
        "server": {"host": "127.0.0.1", "port": _port_from_url(cfg.memory_cfg.get("mnemo_url", ""))},
        "personas": {persona["name"]: {k: v for k, v in persona.items() if k != "name"}},
        "agents": {cfg.business.get("agent_id", cfg.slug): {"persona": persona["name"]}},
    }
    dest = out_dir / "agentb.yaml"
    header = (
        "# Generated by Cortex Harness — Mnemo Cortex backend config.\n"
        "# The persona below IS this business's rule-set. Do not hand-edit;\n"
        "# change harness.config.yaml or the vertical and rebuild.\n"
        "# Add reasoning/embedding provider blocks here (see\n"
        "# mnemo-cortex/agentb.yaml.example) before going to production.\n"
    )
    dest.write_text(header + yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return dest


def _port_from_url(url: str) -> int:
    m = re.search(r":(\d+)", url or "")
    return int(m.group(1)) if m else 50001


def _emit_mcp_json(cfg: HarnessConfig, tools: ResolvedTools, out_dir: Path,
                   brain_dir: Path) -> Path:
    bridge = cfg.mnemo_path / "integrations" / "mcp-bridge" / "server.js"
    env = {
        "MNEMO_URL": cfg.memory_cfg.get("mnemo_url", "http://localhost:50001"),
        "MNEMO_AGENT_ID": cfg.business.get("agent_id", cfg.slug),
        "BRAIN_DIR": str(brain_dir),
        "MNEMO_SHARE": "shared" if cfg.memory_cfg.get("isolation") in ("shared", "hybrid") else "isolated",
        # The harness records the enabled set; hosts/wrappers that honor an
        # allow-list read this. The TOOLS brain lane is the agent-facing copy.
        "HARNESS_ENABLED_TOOLS": ",".join(tools.enabled),
    }
    doc = {
        "mcpServers": {
            "mnemo-cortex": {
                "command": "node",
                "args": [str(bridge)],
                "env": env,
            }
        }
    }
    dest = out_dir / "mcp.json"
    dest.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return dest


def _emit_launchers(cfg: HarnessConfig, out_dir: Path, brain_dir: Path) -> list[Path]:
    mnemo = cfg.mnemo_path
    agentb_yaml = out_dir / "agentb.yaml"
    port = _port_from_url(cfg.memory_cfg.get("mnemo_url", ""))
    written = []

    sh = f"""#!/usr/bin/env bash
# Generated by Cortex Harness. Launches the Mnemo Cortex memory backend for
# "{cfg.business.get('name','')}" using this build's persona + data dir.
set -euo pipefail
MNEMO="{mnemo}"
echo "Starting Mnemo Cortex backend on port {port}..."
( cd "$MNEMO" && python -m agentb.server --config "{agentb_yaml}" ) &
echo
echo "Memory backend launching. Next:"
echo "  • Point your MCP host at: {out_dir / 'mcp.json'}"
echo "  • Brain lanes live in:    {brain_dir}"
wait
"""
    sh_path = out_dir / "start.sh"
    sh_path.write_text(sh, encoding="utf-8")
    written.append(sh_path)

    ps = f"""# Generated by Cortex Harness. Launches the Mnemo Cortex memory backend for
# "{cfg.business.get('name','')}" using this build's persona + data dir.
$Mnemo = "{mnemo}"
Write-Host "Starting Mnemo Cortex backend on port {port}..."
Push-Location $Mnemo
python -m agentb.server --config "{agentb_yaml}"
Pop-Location
Write-Host ""
Write-Host "Point your MCP host at: {out_dir / 'mcp.json'}"
Write-Host "Brain lanes live in:    {brain_dir}"
"""
    ps_path = out_dir / "start.ps1"
    ps_path.write_text(ps, encoding="utf-8")
    written.append(ps_path)
    return written


def _emit_build_readme(cfg: HarnessConfig, tools: ResolvedTools, out_dir: Path,
                       brain_dir: Path) -> Path:
    persona = _resolve_persona(cfg)
    lines = [
        f"# {cfg.business.get('name','')} — compiled harness",
        "",
        f"- **Vertical:** {cfg.vertical.get('title', cfg.vertical_name)} (`{cfg.vertical_name}`)",
        f"- **Agent id:** `{cfg.business.get('agent_id', cfg.slug)}`",
        f"- **Persona / rule-set:** `{persona['name']}`",
        f"- **Tools enabled:** {len(tools.enabled)} ({', '.join(tools.enabled)})",
        "",
        "## Run it",
        "```bash",
        "# 1. Start the memory backend (foreground)",
        f"bash {out_dir.name}/start.sh        # or: ./{out_dir.name}/start.ps1 on Windows",
        "",
        "# 2. Register the MCP server with your agent host",
        f"#    config: {out_dir / 'mcp.json'}",
        "```",
        "",
        "## What's here",
        "- `brain/` — the agent's lanes (identity, rules, tools, playbooks). Editable.",
        "- `agentb.yaml` — memory-backend config carrying the persona rule-set.",
        "- `mcp.json` — MCP registration with only your enabled tools.",
        "- `TOOLS.md` — what the tool loader turned on (and dropped).",
        "",
        "_Regenerate anytime with `python -m harness build`; edits to files here are overwritten._",
    ]
    dest = out_dir / "README.md"
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def _emit_tools_summary(tools: ResolvedTools, out_dir: Path) -> Path:
    # Reuse the agent-facing lane content for the human summary.
    dest = out_dir / "TOOLS.md"
    src = out_dir / "brain" / "tools.md"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def _emit_manifest(cfg: HarnessConfig, tools: ResolvedTools, out_dir: Path,
                   files: list[Path]) -> Path:
    persona = _resolve_persona(cfg)
    doc = {
        "business": cfg.business.get("name"),
        "agent_id": cfg.business.get("agent_id", cfg.slug),
        "vertical": cfg.vertical_name,
        "persona": persona["name"],
        "tools_enabled": tools.enabled,
        "tools_dropped": tools.dropped,
        "warnings": tools.warnings,
        "out_dir": str(out_dir),
    }
    dest = out_dir / "manifest.json"
    dest.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return dest


def compile_build(cfg: HarnessConfig, tools: ResolvedTools,
                  clean: bool = True) -> BuildResult:
    out_dir = cfg.out_dir / cfg.slug
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    brain_dir = out_dir / "brain"
    brain_dir.mkdir(parents=True, exist_ok=True)

    context = _build_context(cfg)
    files: list[Path] = []
    files += _emit_brain(cfg, tools, brain_dir, context)
    files.append(_emit_agentb_yaml(cfg, out_dir))
    files.append(_emit_mcp_json(cfg, tools, out_dir, brain_dir))
    files += _emit_launchers(cfg, out_dir, brain_dir)
    files.append(_emit_tools_summary(tools, out_dir))
    files.append(_emit_build_readme(cfg, tools, out_dir, brain_dir))
    files.append(_emit_manifest(cfg, tools, out_dir, files))

    return BuildResult(out_dir=out_dir, brain_dir=brain_dir, files=files)
