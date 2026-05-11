# AstrBot Notification Plugin

An OpenCode plugin that pushes a message to a QQ chat via [AstrBot](https://github.com/Soulter/AstrBot) when an OpenCode session completes (fires on `session.idle`). Uses AstrBot's cron API to schedule an immediate one-shot message.

## Limitations

The cron-based approach has two structural issues:

1. **No autonomous action.** The cron job simulates a user message (e.g. "output last task result"), waits for the cron session's AI to fill the response, then returns that as a bot reply. This notifies the **human user** visually in QQ, but the **LLM client** driving OpenCode cannot act on it — there is no callback path back to the AI. Since `session.idle` itself already requires user interaction to continue, this is a minor issue in practice, but it means the plugin is purely a notification, not an automation trigger.

2. **Isolated cron session.** The cron job runs in a *separate* AstrBot session, with no visibility into the OpenCode conversation context. It can only report "session XYZ ('title') completed" — not the summary, not the diffs, not any state the AI might need to continue work. Because of limitation #1, this is moot.

**In short:** this plugin tells the user *that* a task finished, but cannot feed the result back to the AI. It is a pragmatic stopgap for QQ-based workflows where the user needs to know when to check back.

**TODO:** Find a notification channel that allows the AI to receive and act on `session.idle` events directly, without relying on simulated user/AI messages in a separate session.

1. AstrBot running and accessible (default `http://10.19.76.1:6185`)
2. AstrBot account credentials (username + password)
3. QQ adapter configured in AstrBot
4. The target QQ chat's `SESSION_ID` — obtained by typing `/sid` in the QQ chat and reading the `UMO` field from the bot's reply.

## How It Works

```
OpenCode session.idle
       │
       ▼
Plugin fetches AstrBot login token (POST /api/auth/login)
       │
       ▼
Plugin schedules a one-shot cron job (POST /api/cron/jobs)
       │
       ▼
AstrBot sends "session completed" message to the QQ chat
```

The password is sent as a 32-char lowercase MD5 hash. The login token is cached in memory until expiry.

## Plugin Code

Place at `~/.config/opencode/plugins/astrbot-notify.js` (global) or `.opencode/plugins/astrbot-notify.js` (project).

```javascript
// astrbot-notify.js — OpenCode → AstrBot → QQ notification plugin
//
// Config: set these environment variables before starting opencode serve.
//   ASTRBOT_URL      — AstrBot base URL (default: http://10.19.76.1:6185)
//   ASTRBOT_USERNAME — AstrBot username
//   ASTRBOT_PASSWORD — AstrBot password (plaintext; MD5 computed internally)
//   ASTRBOT_SESSION  — QQ session ID (get via /sid in QQ chat, use UMO field)
//
// If env vars are not set, the plugin does nothing (graceful no-op).

const crypto = await import("node:crypto")

function md5hex(s) {
  return crypto.createHash("md5").update(s, "utf8").digest("hex").toLowerCase()
}

// ── In-memory token cache ────────────────────────────────────────────

let cachedToken = null
let tokenExpiry = 0

async function getToken(baseUrl, username, password) {
  if (cachedToken && Date.now() < tokenExpiry - 60_000) {
    return cachedToken
  }

  const res = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: username,
      password: md5hex(password),
    }),
  })

  if (!res.ok) {
    throw new Error(`AstrBot login failed: ${res.status}`)
  }

  const json = await res.json()
  if (json.status !== "ok" || !json.data?.token) {
    throw new Error(`AstrBot login unexpected response: ${JSON.stringify(json)}`)
  }

  cachedToken = json.data.token
  // JWT exp claim is in seconds since epoch
  const payload = JSON.parse(Buffer.from(cachedToken.split(".")[1], "base64url").toString())
  tokenExpiry = (payload.exp ?? 0) * 1000

  return cachedToken
}

// ── Plugin entry ─────────────────────────────────────────────────────

export const AstrbotNotify = async ({ client }) => {

  const BASE_URL  = process.env.ASTRBOT_URL ?? "http://10.19.76.1:6185"
  const USERNAME  = process.env.ASTRBOT_USERNAME
  const PASSWORD  = process.env.ASTRBOT_PASSWORD
  const SESSION   = process.env.ASTRBOT_SESSION

  // Graceful no-op if not configured
  if (!USERNAME || !PASSWORD || !SESSION) {
    await client.app.log({
      body: {
        service: "astrbot-notify", level: "warn",
        message: "AstrBot notify plugin loaded but not configured. " +
                 "Set ASTRBOT_USERNAME, ASTRBOT_PASSWORD, and ASTRBOT_SESSION."
      }
    })
    return {}
  }

  await client.app.log({
    body: { service: "astrbot-notify", level: "info", message: "AstrBot notify plugin active." }
  })

  return {
    event: async ({ event }) => {
      if (event.type !== "session.idle") return

      const sessionId = event.session?.id ?? "unknown"
      const sessionTitle = event.session?.title ?? "untitled"

      try {
        const token = await getToken(BASE_URL, USERNAME, PASSWORD)

        const jobBody = {
          run_once: true,
          name: "opencode task done",
          note: [
            `OpenCode session \`${sessionId}\``,
            `"${sessionTitle}"`,
            `completed.`
          ].join(" "),
          cron_expression: "",
          run_at: new Date(Date.now() + 10_000).toISOString(),
          session: SESSION,
          enabled: true,
        }

        const res = await fetch(`${BASE_URL}/api/cron/jobs`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
          },
          body: JSON.stringify(jobBody),
        })

        const body = await res.text()
        await client.app.log({
          body: {
            service: "astrbot-notify",
            level: res.ok ? "info" : "error",
            message: `AstrBot cron job: HTTP ${res.status} — ${body.slice(0, 200)}`,
          }
        })
      } catch (err) {
        await client.app.log({
          body: {
            service: "astrbot-notify",
            level: "error",
            message: `AstrBot notify failed: ${err instanceof Error ? err.message : String(err)}`,
          }
        })
      }
    },
  }
}
```

## Setup Steps

### 1. Get the QQ session ID

In the target QQ chat window, send:

```
/sid
```

The bot replies with a message containing `UMO: XXXXXXXXXXXXXXXX`. That string is the `ASTRBOT_SESSION`.

### 2. Set environment variables

```bash
export ASTRBOT_URL="http://10.19.76.1:6185"
export ASTRBOT_USERNAME="astrbot"
export ASTRBOT_PASSWORD="your-plaintext-password"
export ASTRBOT_SESSION="QQ:FriendMessage:XXXXXXXX"
```

### 3. Restart opencode serve

```bash
python scripts/main.py restart
```

## Verification

Fire a trivial task and watch the QQ chat:

```bash
SID=$(python scripts/main.py fire "Say hello and exit.")
python scripts/main.py wait $SID
```

AstrBot should send a message to the QQ chat when the session completes. Check logs:

```bash
# In the opencode serve terminal output, look for:
# [astrbot-notify] AstrBot cron job: HTTP 200 — ...
```
