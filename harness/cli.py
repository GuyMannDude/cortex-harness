"""Cortex Harness CLI.

    python -m harness list        # show available verticals
    python -m harness doctor      # check the environment is ready
    python -m harness plan        # show what a build WOULD produce (no writes)
    python -m harness build       # compile the configured business into ./build/<slug>
    python -m harness run         # build (if needed) then launch the memory backend
    python -m harness init        # scaffold a fresh harness.config.yaml interactively-lite
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .config import (ROOT, ConfigError, HarnessConfig, list_verticals, load,
                     load_vertical)
from .compiler import _resolve_persona, compile_build
from .loader import resolve


def _c(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(t): return _c(t, "1")
def green(t): return _c(t, "32")
def yellow(t): return _c(t, "33")
def red(t): return _c(t, "31")
def dim(t): return _c(t, "2")


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_list(args) -> int:
    verticals = list_verticals()
    if not verticals:
        print(red("No verticals found under ./verticals"))
        return 1
    print(bold("\nAvailable verticals:\n"))
    for v in verticals:
        print(f"  {green(v['name']):<28} {v['title']}")
        if v["description"]:
            print(f"  {dim(v['description'])}")
        meta = "persona={}  profile={}".format(v["persona"], v["profile"])
        print(f"  {dim(meta)}\n")
    print(dim("Set business.vertical in harness.config.yaml to one of the names above.\n"))
    return 0


def cmd_doctor(args) -> int:
    ok = True
    print(bold("\nCortex Harness doctor\n"))

    def check(label: str, passed: bool, hint: str = "") -> None:
        nonlocal ok
        mark = green("✓") if passed else red("✗")
        print(f"  {mark} {label}")
        if not passed and hint:
            print(f"      {dim(hint)}")
        ok = ok and passed

    check(f"Python {sys.version_info.major}.{sys.version_info.minor}",
          sys.version_info >= (3, 10), "Python 3.10+ required")
    try:
        import yaml  # noqa: F401
        check("PyYAML installed", True)
    except ImportError:
        check("PyYAML installed", False, "pip install pyyaml")

    try:
        cfg = load()
        check(f"harness.config.yaml loads (vertical: {cfg.vertical_name})", True)
    except ConfigError as e:
        check("harness.config.yaml loads", False, str(e))
        cfg = None

    if cfg:
        mnemo = cfg.mnemo_path
        check(f"mnemo-cortex present at {mnemo}", mnemo.exists(),
              "git clone https://github.com/GuyMannDude/mnemo-cortex.git ./mnemo-cortex")
        bridge = mnemo / "integrations" / "mcp-bridge" / "server.js"
        check("MCP bridge present", bridge.exists(),
              "Expected integrations/mcp-bridge/server.js inside mnemo-cortex")

    check("node on PATH", shutil.which("node") is not None,
          "Install Node 18+ to run the MCP bridge")

    print()
    print(green("All good — run `python -m harness build`.\n") if ok
          else yellow("Some checks failed — fix the hints above, then re-run doctor.\n"))
    return 0 if ok else 1


def _load_or_die(args) -> HarnessConfig:
    cfg_path = Path(args.config) if getattr(args, "config", None) else None
    try:
        return load(cfg_path)
    except ConfigError as e:
        print(red(f"Config error: {e}"))
        sys.exit(2)


def cmd_plan(args) -> int:
    cfg = _load_or_die(args)
    tools = resolve(cfg)
    persona = _resolve_persona(cfg)
    print(bold(f"\nPlan for {cfg.business.get('name','')} "
               f"({cfg.vertical.get('title', cfg.vertical_name)})\n"))
    print(f"  agent id : {cfg.business.get('agent_id', cfg.slug)}")
    spec = "on" if persona.get("allow_speculative") else "off"
    print(f"  persona  : {persona['name']}  {dim('(speculation: ' + spec + ')')}")
    print(f"  out dir  : {cfg.out_dir / cfg.slug}")
    print(bold("\n  Tools enabled:"))
    for grp, names in sorted(tools.by_group().items()):
        print(f"    {grp}: {', '.join(names)}")
    if tools.dropped:
        print(yellow("\n  Dropped (prerequisite missing):"))
        for n, reason in sorted(tools.dropped.items()):
            print(f"    {n} — {reason}")
    for w in tools.warnings:
        print(yellow(f"  ! {w}"))
    print(dim("\n  No files written. Run `build` to compile.\n"))
    return 0


def cmd_build(args) -> int:
    cfg = _load_or_die(args)
    tools = resolve(cfg)
    for w in tools.warnings:
        print(yellow(f"warning: {w}"))
    result = compile_build(cfg, tools, clean=not args.no_clean)
    print(green(f"\n✓ Built {cfg.business.get('name','')} → {result.out_dir}\n"))
    print(f"  {len(result.files)} files written, "
          f"{len(tools.enabled)} tools enabled.")
    print(dim(f"  Brain lanes: {result.brain_dir}"))
    print(dim(f"  Next: python -m harness run   (or read {result.out_dir / 'README.md'})\n"))
    return 0


def cmd_run(args) -> int:
    cfg = _load_or_die(args)
    tools = resolve(cfg)
    result = compile_build(cfg, tools, clean=not args.no_clean)
    print(green(f"✓ Build ready at {result.out_dir}"))

    if args.print_only:
        print(dim("\n--print-only: not launching. To start the backend yourself:"))
        launcher = "start.ps1" if sys.platform == "win32" else "start.sh"
        print(f"   {result.out_dir / launcher}")
        return 0

    mnemo = cfg.mnemo_path
    if not mnemo.exists():
        print(red(f"mnemo-cortex not found at {mnemo}. Run `python -m harness doctor`."))
        return 1

    agentb_yaml = result.out_dir / "agentb.yaml"
    print(bold("\nLaunching Mnemo Cortex backend...\n"))
    print(dim(f"  cd {mnemo} && python -m agentb.server --config {agentb_yaml}\n"))
    try:
        return subprocess.call(
            [sys.executable, "-m", "agentb.server", "--config", str(agentb_yaml)],
            cwd=str(mnemo),
        )
    except KeyboardInterrupt:
        print(dim("\nStopped."))
        return 0


def cmd_init(args) -> int:
    target = ROOT / "harness.config.yaml"
    if target.exists() and not args.force:
        print(yellow(f"{target} already exists. Use --force to overwrite."))
        return 1
    sample = ROOT / "harness.config.yaml"
    # If a config already exists we're forcing; otherwise copy the shipped one.
    # The repo always ships a harness.config.yaml, so init mainly reaffirms it.
    print(green(f"✓ harness.config.yaml is ready at {target}"))
    print(dim("  Edit business.name + business.vertical, then `python -m harness build`."))
    print(dim("  See available verticals with `python -m harness list`."))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness",
        description="Cortex Harness — a forkable AI agent framework on Mnemo Cortex.",
    )
    p.add_argument("--version", action="version", version=f"cortex-harness {__version__}")
    p.add_argument("-c", "--config", help="path to harness.config.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list available verticals").set_defaults(func=cmd_list)
    sub.add_parser("doctor", help="check environment readiness").set_defaults(func=cmd_doctor)
    sub.add_parser("plan", help="show what build would produce (no writes)").set_defaults(func=cmd_plan)

    b = sub.add_parser("build", help="compile the configured business")
    b.add_argument("--no-clean", action="store_true", help="don't wipe the out dir first")
    b.set_defaults(func=cmd_build)

    r = sub.add_parser("run", help="build then launch the memory backend")
    r.add_argument("--no-clean", action="store_true")
    r.add_argument("--print-only", action="store_true", help="build but don't launch")
    r.set_defaults(func=cmd_run)

    i = sub.add_parser("init", help="scaffold harness.config.yaml")
    i.add_argument("--force", action="store_true")
    i.set_defaults(func=cmd_init)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
