# Cortex Harness

**A forkable, generic AI-agent framework built on the [Mnemo Cortex](https://github.com/GuyMannDude/mnemo-cortex) memory layer.**

Fork it, pick a vertical, edit **one** config file, build, and run. You get an
agent with persistent memory, a business-specific rule-set, and a tool-set
scoped to what you turned on.

```
┌─────────────────────────────────────────────────────────────┐
│  harness.config.yaml   ←  the one file you edit               │
│        │                                                      │
│        ▼                                                      │
│  ┌───────────┐   pick a vertical   ┌──────────────────────┐  │
│  │  COMPILER │ ◀────────────────── │ verticals/<vertical> │  │
│  └─────┬─────┘   + tool loader     │  brain templates     │  │
│        │                           │  rules.md (rule-set) │  │
│        ▼                           │  vertical.yaml       │  │
│  build/<you>/                      └──────────────────────┘  │
│    brain/        rendered lanes (identity, rules, tools, …)   │
│    agentb.yaml   memory backend config (persona = rule-set)   │
│    mcp.json      MCP registration with your enabled tools     │
│    start.sh/.ps1 launch the memory backend                    │
│        │                                                      │
│        ▼                                                      │
│  Mnemo Cortex  ── persistent memory · facts · brain lanes ──  │
└─────────────────────────────────────────────────────────────┘
```

## Why

Every AI agent starts from zero each session. Mnemo Cortex fixes the amnesia.
**Cortex Harness** is the layer on top that turns that memory into a *product you
can ship for a specific business* — without rewiring anything. The three things
every business needs to customize are first-class:

| Concept | Where it lives | What it does |
|---|---|---|
| 🧠 **Brain templates** | `verticals/<v>/brain/*.md` | The agent's identity, playbooks, and reference lanes. Markdown with `{{placeholders}}`. |
| 📏 **Rule sets** | `verticals/<v>/rules.md` + `personas` | How cautious the agent is, what it may speculate on, what needs human sign-off. Compiles into a Mnemo persona. |
| 🔧 **Tool loader** | `harness/tools_catalog.yaml` + `tools:` | Enable only the memory-layer tools you need. Profiles + per-business enable/disable, with prerequisite validation. |

## Quickstart

```bash
# 0. You already cloned the memory layer:
#    git clone https://github.com/GuyMannDude/mnemo-cortex.git ./mnemo-cortex

# 1. Install the harness CLI deps (PyYAML only)
pip install -r requirements.txt        # or: pip install -e .

# 2. See what you can build
python -m harness list

# 3. Check your environment is ready
python -m harness doctor

# 4. Edit harness.config.yaml — set business.name + business.vertical

# 5. Preview, then compile
python -m harness plan
python -m harness build

# 6. Run (builds, then launches the Mnemo Cortex backend)
python -m harness run
#    Then point your MCP host at build/<you>/mcp.json
```

## The one file you edit

[`harness.config.yaml`](harness.config.yaml) — name your business, pick a vertical,
choose a tool profile, and (optionally) a persona. Everything else is derived.

```yaml
business:
  name: "Acme Co."
  vertical: small-business      # python -m harness list
  agent_id: acme-assistant
tools:
  profile: standard             # minimal | standard | full
  enable: []
  disable: []
rules:
  persona: ""                   # blank = use the vertical's recommended rule-set
memory:
  isolation: isolated           # isolated | shared | hybrid
```

## Verticals shipped

| Vertical | For | Default rule-set |
|---|---|---|
| `small-business` | Customers, quotes, scheduling, follow-ups | `operator` — concise, fact-checked, approval-gated |
| `ecommerce` | Catalog, inventory, orders, support | `merchant` — SKUs/prices/stock as facts |
| `art-studio` | Commissions + a creative muse | `studio` — speculative muse / exact business |
| `writing` | Drafting + canon/continuity keeping | `editor` — generative but ruthless on continuity |
| `day-trading` | Trading **journal & research desk** | `risk_desk` — analysis only, never executes, enforces your rules |

Each vertical is just a folder. **Adding your own is the point** (see below).

## CLI

| Command | Does |
|---|---|
| `harness list` | List available verticals |
| `harness doctor` | Check Python, PyYAML, mnemo-cortex, Node |
| `harness plan` | Show what a build *would* produce — no writes |
| `harness build` | Compile to `build/<slug>/` |
| `harness run` | Build, then launch the memory backend |
| `harness init` | (Re)affirm `harness.config.yaml` |

## How the tool loader works

`harness/tools_catalog.yaml` catalogs every Mnemo Cortex tool with a group, usage
guidance, and prerequisites. You pick a **profile** (`minimal`/`standard`/`full`),
then layer `enable:`/`disable:`. The loader validates prerequisites against your
deployment — e.g. `mnemo_share` is dropped unless `memory.isolation` is `shared`,
and bus tools are dropped unless a bus is configured. The result is written to:

- `mcp.json` → a `HARNESS_ENABLED_TOOLS` allow-list + a bridge pointed at your brain dir
- `brain/tools.md` → the agent-facing lane describing exactly what's on

Run `harness plan` to see enabled vs. dropped (with reasons) before building.

> **On enforcement (today):** the enabled set scopes the agent through its
> *instructions* — `brain/tools.md` tells it exactly which tools to use — and is
> recorded in `mcp.json` as `HARNESS_ENABLED_TOOLS` for hosts that honor an
> allow-list. Hard host-level gating (the Mnemo Cortex bridge filtering tool
> registration down to the allow-list) is on the roadmap; until then, treat the
> tool loader as scoping + documentation, not a hard security boundary.

## Add your own vertical

```
verticals/my-vertical/
  vertical.yaml        # title, description, recommended persona/profile, custom personas
  rules.md             # your business rule-set (markdown, supports {{placeholders}})
  brain/
    00-identity.md     # who the agent is
    20-playbook.md     # how it works day to day
```

Everything in `verticals/_base/` is inherited automatically (shared identity,
memory protocol, and base rules), so a new vertical only states what's different.
Then set `business.vertical: my-vertical` and build. That's the whole extension
model — **fork, copy a vertical, customize, run.**

## Layout

```
harness.config.yaml      # the one file you edit
harness/                 # the framework engine (Python, PyYAML-only)
  tools_catalog.yaml     #   the tool loader's source of truth
  config.py loader.py compiler.py cli.py
verticals/               # brain templates + rule sets per business type
  _base/                 #   shared foundation every vertical inherits
  small-business/ ecommerce/ art-studio/ writing/ day-trading/
mnemo-cortex/            # the memory layer (cloned dependency)
build/                   # compiled, runnable workspaces (generated)
```

## Requirements

- Python 3.10+ and PyYAML (the CLI)
- Node 18+ (the Mnemo Cortex MCP bridge)
- A running Mnemo Cortex backend — `harness run` launches it for you; see
  [`mnemo-cortex/agentb.yaml.example`](mnemo-cortex/agentb.yaml.example) to wire
  up reasoning/embedding providers before production.

## License

MIT (the harness). Mnemo Cortex is MIT under its own repository.
