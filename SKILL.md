---
name: opencode-skill
description: Guide AI on how to use the OpenCode CLI to execute complex tasks (not limited to coding). Covers external mode (user provides OPENCODE_API_URL) and managed mode (AI spawns opencode serve). All interaction goes through the bundled scripts/main.py Python CLI wrapper. This skill should be used when the user asks to automate tasks with OpenCode CLI, run headless agents, configure MCP/skills/plugins, or integrate OpenCode into scripts and workflows.
agent_created: true
---

# OpenCode Skill

Use the bundled `scripts/main.py` to delegate tasks to an `opencode serve` instance via HTTP. Two modes:

| Mode | Trigger | Server lifecycle |
|------|---------|-----------------|
| Managed | `mode: "managed"` in config | Script spawns/kills/restarts transparently |
| External | `mode: "external"` in config | Script connects to an existing server, never touches its process |

## 1. Startup

### 1.1 Write the config file

The script reads `opencode-config.json` from the same directory as `main.py`. If it's missing, the script prints an error with instructions. Create it:

**Managed mode** (recommended — script owns the server):
```json
{
  "mode": "managed",
  "url": "http://127.0.0.1:4096",
  "password": null,
  "username": "opencode",
  "port": 4096,
  "hostname": "127.0.0.1",
  "default_provider": "deepseek",
  "default_model": "deepseek-v4-pro"
}
```

**External mode** (user provides `OPENCODE_API_URL`):
```json
{
  "mode": "external",
  "url": "http://10.0.0.5:4096",
  "password": "secret",
  "username": "opencode",
  "default_provider": "deepseek",
  "default_model": "deepseek-v4-pro"
}
```

A template lives at `scripts/opencode-config.example.json`. Write the config to `scripts/opencode-config.json` before any other command. Fail early if the user hasn't provided a provider/model and no default is known.

### 1.2 Verify

```bash
python scripts/main.py status
```

In managed mode, the first command auto-spawns the server if it's not running. In external mode, it checks connectivity to the provided URL.

## 2. Task Execution

All commands take optional `--dir` / `-d` to target a project directory.

**Guidance:** Use `fire` (async) for anything non-trivial. Reserve `ask` (sync) for trivial one-line queries. The most proactive approach: install a notification plugin (see 2.3) so OpenCode *pushes* completion events to the LLM, avoiding blocking on `wait` entirely.

### 2.1 One-shot query (blocking — trivial tasks only)

```bash
python scripts/main.py ask "What does git status do?"
python scripts/main.py ask "..." --agent plan
python scripts/main.py ask "Review the schema" --dir /home/user/other-project
```

### 2.2 Async fire + wait (practical default)

For any task involving code changes, file creation, refactoring, or multi-step reasoning — fire asynchronously, then wait:

```bash
# Fire and get session ID
SID=$(python scripts/main.py fire "Refactor the auth module to use JWT")
# => prints session ID to stdout

# Wait until done (blocks, prints result)
python scripts/main.py wait $SID

# Or check progress without blocking
python scripts/main.py check $SID
# => Status: running
#    Tasks: 2/5 completed, 1 in progress
#      Current: Refactor auth middleware
```

Note: `wait` blocks the LLM's tool call. If the task is very long and the LLM client times out tool calls, prefer the notification approach below, or fall back to periodic `check` calls.

### 2.3 Notification plugin (most proactive — when LLM client supports it)

Rather than blocking on `wait`, install a plugin that hooks `session.idle` and pushes a notification to the LLM. The LLM fires a task, continues other work, and receives a callback when OpenCode finishes.

Template (adapt `NOTIFY_FN` body to the LLM client's available notification channel):

```javascript
// ~/.config/opencode/plugins/notify-session-idle.js
export const NotifySessionIdle = async ({ client }) => {

  const NOTIFY_FN = async (sessionId, sessionTitle) => {
    // --- Adapt this block to the notification channel available ---
    //
    // Option A: HTTP webhook (Slack, Discord, custom endpoint)
    //   await fetch("https://hooks.example.com/notify", {
    //     method: "POST", headers: {"Content-Type": "application/json"},
    //     body: JSON.stringify({ text: `OpenCode session ${sessionId} ("${sessionTitle}") completed.` })
    //   })
    //
    // Option B: Desktop notification (macOS)
    //   Bun.$`osascript -e 'display notification "OpenCode done: ${sessionTitle}" with title "OpenCode"'`
    //
    // Option C: Write to a file the LLM is watching
    //   await Bun.write("/tmp/opencode-events.jsonl", JSON.stringify({ event: "session.idle", sessionId, sessionTitle }) + "\n")
    //
    // Option D: AstrBot cron (for QQ/WeChat bots)
    //   await fetch("http://BOT_URL:6185/api/cron/jobs", { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer TOKEN"}, body: JSON.stringify({ run_once: true, name: "opencode done", note: `Session ${sessionId} ("${sessionTitle}") completed.`, run_at: new Date(Date.now() + 10_000).toISOString(), session: "QQ:FriendMessage:XXXXX", enabled: true }) })
    // --------------------------------------------------------------
    throw new Error("NOTIFY_FN not implemented — adapt to your notification channel.")
  }

  return {
    event: async ({ event }) => {
      if (event.type !== "session.idle") return
      const sessionId = event.session?.id ?? "unknown"
      const sessionTitle = event.session?.title ?? "untitled"
      try {
        await NOTIFY_FN(sessionId, sessionTitle)
        await client.app.log({
          body: { service: "notify-session-idle", level: "info",
                  message: `Notified: session ${sessionId} idle.` }
        })
      } catch (err) {
        await client.app.log({
          body: { service: "notify-session-idle", level: "error",
                  message: `Notify failed: ${err.message}` }
        })
      }
    }
  }
}
```

After writing this plugin (delegate to an OpenCode session + restart), the LLM's workflow becomes:

```bash
SID=$(python scripts/main.py fire "Build the user management API")
# LLM continues other work immediately — no blocking
# ... later, notification arrives: "session SID completed"
python scripts/main.py diffs $SID
python scripts/main.py conversation $SID
```

For a complete AstrBot + QQ notification implementation (login → token → cron), see `references/astrbot-notify.md`.

### 2.4 Session management

```bash
python scripts/main.py session list
python scripts/main.py session get <sid>
python scripts/main.py session delete <sid>
python scripts/main.py session fork <sid>
python scripts/main.py session fork <sid> --message-id <mid>
python scripts/main.py session abort <sid>
```

## 3. File Operations

```bash
python scripts/main.py read src/auth.ts
python scripts/main.py ls src/
python scripts/main.py find "auth.*token"
python scripts/main.py find-file "config"
python scripts/main.py find-symbol "login"
python scripts/main.py read path/to/file --dir /other-project
```

## 4. Configuration (runtime, no restart needed)

```bash
python scripts/main.py config              # GET /config
python scripts/main.py config-set '{"model":"anthropic/claude-sonnet-4-5"}'
python scripts/main.py providers           # List providers with status
python scripts/main.py agents              # List agents
python scripts/main.py mcp-status          # MCP server status
python scripts/main.py mcp-add my-server '{"type":"remote","url":"https://..."}'
```

`config-set` and `mcp-add` take effect immediately, no restart required.

## 5. Configuration Delegation (disk changes)

For changes that write files to disk — skills, plugins, custom tools, custom agents (markdown) — delegate the file creation to an OpenCode session, then restart:

```
# Step 1: Ask OpenCode to create the files
python scripts/main.py ask "Create .opencode/skills/git-release/SKILL.md ..." --dir /project

# Step 2: Restart to pick up new files (managed mode only)
python scripts/main.py restart
```

In **external mode**, `restart` will error. Tell the user to restart `opencode serve` manually after the files are written.

### 5.1 What needs restart vs what doesn't

| Change | Method | Restart? |
|--------|--------|----------|
| Update config (models, permissions, etc.) | `config-set` | No |
| Add MCP server | `mcp-add` | No |
| Set provider credentials | `config-set` | No |
| Agent defined in `opencode.json` | `config-set` | No |
| Skills (SKILL.md in directories) | Delegate to session | **Yes** |
| Plugins (JS/TS in directories) | Delegate to session | **Yes** |
| Custom tools (TS/JS in directories) | Delegate to session | **Yes** |
| Custom agents (Markdown) | Delegate to session | **Yes** |

### 5.2 Example delegation prompts

**MCP server** (runtime, no restart):
```bash
python scripts/main.py mcp-add sentry '{"type":"remote","url":"https://mcp.sentry.dev/mcp","oauth":{}}'
```

**Plugin** (disk, needs restart):
```bash
python scripts/main.py ask "Create .opencode/plugins/notification.js with a plugin that sends desktop notifications on session.idle events." --dir /project
python scripts/main.py restart
```

**Custom agent** (markdown, needs restart):
```bash
python scripts/main.py ask "Create .opencode/agents/code-reviewer.md as a subagent with edit:deny and bash:deny permissions." --dir /project
python scripts/main.py restart
```

**Custom agent** (JSON in config, no restart):
```bash
python scripts/main.py config-set '{"agent":{"reviewer":{"description":"...","mode":"subagent"}}}'
```

## 6. Server Management (managed mode)

```bash
python scripts/main.py status      # Check health
python scripts/main.py restart     # Kill + spawn + wait healthy
```

In managed mode, every command calls `main.py` checks if the server is alive before proceeding. If it has died, the script transparently spawns a new instance. The LLM does not need to check health manually.

## 7. Complete Command Reference

**Task execution:**
`ask` `fire` `wait` `check` `todo` `diffs` `conversation`

**Session:**
`session list` `session get <id>` `session delete <id>` `session fork <id>` `session abort <id>`

**Files:**
`read <path>` `ls [path]` `find "<pat>"` `find-file "<name>"` `find-symbol "<name>"`

**Config:**
`config` `config-set <json>` `providers` `agents` `mcp-status` `mcp-add <name> <json>`

**Server:**
`status` `restart`

All commands accept `--dir` / `-d` for multi-project targeting. `ask` and `fire` additionally accept `--model` / `-m` and `--agent` / `-a`.

---

For the raw HTTP API and CLI command reference, see:
- `references/http-api.md`
- `references/cli-reference.md`
