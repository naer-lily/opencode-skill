# OpenCode Server HTTP API Reference

Base URL: `http://127.0.0.1:4096`. All endpoints accept `x-opencode-directory` header for multi-project targeting.

Authentication (if `OPENCODE_SERVER_PASSWORD` is set):

```
Authorization: Basic <base64(opencode:password)>
```

## Health & Instance

```
GET  /global/health              → { healthy: boolean, version: string }
POST /instance/dispose           → boolean (graceful shutdown)
```

## Sessions

```
GET    /session                  → Session[]
POST   /session                  → Session
  Body: { parentID?, title? }
GET    /session/:id              → Session
DELETE /session/:id              → boolean
PATCH  /session/:id              → Session  (Body: { title? })
GET    /session/:id/children     → Session[]
GET    /session/:id/todo         → Todo[]
POST   /session/:id/init         → boolean  (Body: { messageID, providerID, modelID })
POST   /session/:id/fork         → Session  (Body: { messageID? })
POST   /session/:id/abort        → boolean
POST   /session/:id/share        → Session
DELETE /session/:id/share        → Session
POST   /session/:id/revert       → boolean  (Body: { messageID, partID? })
POST   /session/:id/unrevert     → boolean
POST   /session/:id/summarize    → boolean  (Body: { providerID, modelID })
POST   /session/:id/permissions/:pid → boolean  (Body: { response, remember? })
```

## Messages

```
GET    /session/:id/message              → MessageList  (Query: limit?)
POST   /session/:id/message              → MessageResponse (sync, blocks)
  Body: { parts, messageID?, model?, agent?, system?, tools?, noReply? }
POST   /session/:id/prompt_async         → 204 No Content (async)
  Body: { parts, messageID?, model?, agent?, system?, tools? }
GET    /session/:id/message/:msgID      → MessageResponse
POST   /session/:id/command              → MessageResponse
  Body: { command, arguments?, messageID?, agent?, model? }
POST   /session/:id/shell                → MessageResponse
  Body: { command, agent, model? }
```

### Parts format

```json
{
  "parts": [
    {"type": "text", "text": "Hello"},
    {"type": "file", "path": "/abs/path/to/file.ts"}
  ],
  "model": {"providerID": "anthropic", "modelID": "claude-sonnet-4-5"},
  "agent": "build"
}
```

## Files & Search

```
GET /file?path=<dir>             → FileNode[]
GET /file/content?path=<path>    → FileContent
GET /file/status                 → File[]
GET /find?pattern=<regex>        → Match[]
GET /find/file?query=<q>         → string[]
  Query: type? limit? directory? dirs?
GET /find/symbol?query=<q>       → Symbol[]
```

## Config & Providers

```
GET    /config                   → Config (secrets redacted)
PATCH  /config                   → Config (partial update)
GET    /config/providers         → { providers: Provider[], default }
GET    /provider                 → { all, default, connected }
GET    /provider/auth            → { [id]: ProviderAuthMethod[] }
POST   /provider/:id/oauth/authorize → authorization URL
POST   /provider/:id/oauth/callback  → boolean
PUT    /auth/:id                 → boolean (set credentials)
```

## Agents, Commands, MCP, LSP

```
GET    /agent                    → Agent[]
GET    /command                  → Command[]
GET    /mcp                      → { [name]: MCPStatus }
POST   /mcp                      → MCP status (Body: { name, config })
GET    /lsp                      → LSPStatus[]
GET    /formatter                → FormatterStatus[]
```

## Projects

```
GET    /project                  → Project[]
GET    /project/current          → Project
GET    /path                     → Path
GET    /vcs                      → VcsInfo
```

## Events (SSE)

```
GET    /event                    → SSE stream
GET    /global/event             → SSE stream
```

## Tools (Experimental)

```
GET    /experimental/tool/ids
GET    /experimental/tool?provider=p&model=m
```

## Logging

```
POST   /log                      → boolean
  Body: { service, level, message, extra? }
```

## TUI Control

```
POST   /tui/append-prompt    Body: { text }
POST   /tui/submit-prompt
POST   /tui/clear-prompt
POST   /tui/execute-command  Body: { command }
POST   /tui/show-toast       Body: { title?, message, variant? }
POST   /tui/open-help
POST   /tui/open-sessions
POST   /tui/open-models
POST   /tui/open-themes
GET    /tui/control/next
POST   /tui/control/response Body: { body }
```
