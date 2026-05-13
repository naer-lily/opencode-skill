# AstrBot Notification Plugin

An OpenCode plugin that pushes a message to a QQ chat via [AstrBot](https://github.com/Soulter/AstrBot) when an OpenCode session completes (fires on `session.idle`).

Uses the [external_trigger](https://github.com/naer-lily/astrbot_plugin_external_trigger) AstrBot plugin — a single webhook call injects a message directly into the target conversation, no cron scheduling or JWT login needed.

## Prerequisites

1. AstrBot running with `astrbot_plugin_external_trigger` installed and enabled
   ```bash
   cd /AstrBot/data/plugins
   git clone https://github.com/naer-lily/astrbot_plugin_external_trigger
   # Enable in dashboard
   ```
2. AstrBot API key — get from dashboard: Settings → API Token
3. The target QQ chat's `UMO` — send `/sid` in the chat, copy the `UMO` value

## How It Works

```
OpenCode session.idle
       │
       ▼
Plugin POSTs to AstrBot webhook (POST /api/v1/plug/hook/external-event)
  Authorization: Bearer <API_KEY>
  Body: { umo: "QQ:FriendMessage:XXXX", message: "..." }
       │
       ▼
AstrBot injects the message into the target chat → LLM replies directly
```

Single HTTP call, no login round-trip, no cron scheduling.

## Plugin Code

Place at `~/.config/opencode/plugins/astrbot-notify.js` (global) or `.opencode/plugins/astrbot-notify.js` (project).

```javascript
// astrbot-notify.js — OpenCode → AstrBot → QQ notification plugin
//
// Requires astrbot_plugin_external_trigger installed on AstrBot.
//
// Env vars:
//   ASTRBOT_URL      — AstrBot base URL (default: http://10.19.76.1:6185)
//   ASTRBOT_API_KEY  — AstrBot API token (from dashboard)
//   ASTRBOT_SESSION  — QQ session UMO (get via /sid in QQ chat)
//
// If env vars are not set, the plugin does nothing (graceful no-op).

// ── Plugin entry ─────────────────────────────────────────────────────

export const AstrbotNotify = async ({ client }) => {

  const BASE_URL  = process.env.ASTRBOT_URL ?? "http://10.19.76.1:6185"
  const API_KEY   = process.env.ASTRBOT_API_KEY
  const SESSION   = process.env.ASTRBOT_SESSION

  if (!API_KEY || !SESSION) {
    await client.app.log({
      body: {
        service: "astrbot-notify", level: "warn",
        message: "AstrBot notify plugin loaded but not configured. " +
                 "Set ASTRBOT_API_KEY and ASTRBOT_SESSION."
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

      const sessionID = event.properties?.sessionID ?? "unknown"
      let sessionTitle = "untitled"
      try {
        const session = await client.session.get({ path: { id: sessionID } })
        sessionTitle = session.data?.title || "untitled"
      } catch (_) { /* fallback */ }

      const message = [
        `OpenCode session \`${sessionID}\` ("${sessionTitle}") completed.`,
        `IMPORTANT: The webhook result is NOT visible to the user —`,
        `it is only visible to you. You MUST use the send_message_to_user`,
        `tool to directly notify the user that the task is done, including`,
        `a summary of the results. After notifying, perform any follow-up`,
        `actions if needed.`,
      ].join(" ")

      try {
        const res = await fetch(
          `${BASE_URL}/api/v1/plug/hook/external-event`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Authorization": `Bearer ${API_KEY}`,
            },
            body: JSON.stringify({ umo: SESSION, message }),
          },
        )

        const body = await res.text()
        await client.app.log({
          body: {
            service: "astrbot-notify",
            level: res.ok ? "info" : "error",
            message: `AstrBot webhook: HTTP ${res.status} — ${body.slice(0, 200)}`,
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

### 1. Install the external_trigger plugin on AstrBot

```bash
cd /AstrBot/data/plugins
git clone https://github.com/naer-lily/astrbot_plugin_external_trigger
```

Enable it in the AstrBot dashboard. The startup log should show:

```
[external_trigger] JWT endpoint ready: POST /api/plug/hook/external-event
[external_trigger] API-key endpoint ready: POST /api/v1/plug/hook/external-event
```

### 2. Get the API key

Dashboard → Settings → API Token. Copy the token.

### 3. Get the QQ session UMO

In the target QQ chat, send:

```
/sid
```

The bot replies with a message containing `UMO: XXXXXXXXXXXXXXXX`. That string is the `ASTRBOT_SESSION`.

### 4. Set environment variables

```bash
export ASTRBOT_URL="http://10.19.76.1:6185"
export ASTRBOT_API_KEY="your-api-token"
export ASTRBOT_SESSION="QQ:FriendMessage:XXXXXXXX"
```

### 5. Restart opencode serve

```bash
python scripts/main.py restart
```

## Verification

Fire a trivial task and watch the QQ chat:

```bash
SID=$(python scripts/main.py fire "Say hello and exit.")
# Notification arrives in QQ when session completes
```

Check the OpenCode serve logs for the plugin log lines.
