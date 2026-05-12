# opencode-skill

An [OpenCode](https://opencode.ai) agent skill that teaches an LLM how to use OpenCode programmatically — via a bundled Python CLI wrapper over the headless HTTP API.

## What it does

Wraps every `opencode serve` HTTP operation into a single Python script (`scripts/main.py`), so the LLM never needs to handcraft curl calls. Covers:

- **Task execution** — `ask` (sync), `fire` (async), `check` (progress peek), `--sid` session reuse
- **Session management** — list, get, delete, fork, abort
- **File operations** — read, list directory, grep, fuzzy file/symbol search
- **Runtime config** — read/update config, list providers/agents, add MCP servers dynamically
- **Disk config delegation** — ask OpenCode to write skills/plugins/tools/agents, then restart

## Two modes

| Mode | How | Server lifecycle |
|------|-----|-----------------|
| **Managed** | `"mode": "managed"` in config | Script spawns, health-checks, and restarts `opencode serve` transparently |
| **External** | `"mode": "external"` in config | Connects to an existing `opencode serve` (e.g., user provides `OPENCODE_API_URL`) |

## Quick start

```
skills/opencode-skill/
├── SKILL.md                           # LLM instructions
├── scripts/
│   ├── main.py                        # Python CLI (pip install requests)
│   └── opencode-config.example.json   # Config template
└── references/
    ├── http-api.md                    # Full HTTP endpoint reference
    ├── cli-reference.md               # opencode CLI commands
    └── astrbot-notify.md              # QQ notification plugin for AstrBot
```

```bash
# 1. Write the config
cp scripts/opencode-config.example.json scripts/opencode-config.json
# Edit default_provider / default_model to match your setup

# 2. Verify
python scripts/main.py status

# 3. **IMPORTANT** — Sessions WILL hang on permission requests.
# Permissions are FILE-CONFIG ONLY. Add this to opencode.json before starting serve:
#
#   "permission": "allow"
#
# Without this, external_directory access and other guarded operations
# will cause sessions to hang indefinitely. If you cannot accept this,
# do NOT use this skill.

# 4. Ask a question
python scripts/main.py ask "Explain the auth flow"

# 5. Fire a long task asynchronously
SID=$(python scripts/main.py fire "Refactor the auth module")
python scripts/main.py check $SID
```

## Install

```bash
git clone git@github.com:naer-lily/opencode-skill.git ~/.config/opencode/skills/opencode-skill
```

Make sure `pip install requests` and `opencode` are on your PATH.
