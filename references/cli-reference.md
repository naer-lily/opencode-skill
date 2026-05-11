# OpenCode CLI Command Reference

Commands that operate outside the HTTP API: server lifecycle, auth, package management, data export.

## Server Management

```bash
opencode serve --port 4096                         # Start headless
opencode serve --port 4096 --hostname 0.0.0.0      # Listen on network
OPENCODE_SERVER_PASSWORD=secret opencode serve &    # With auth, background
pkill -f "opencode serve"                           # Kill server
```

## Provider Auth

```bash
opencode auth login                     # Interactive setup
opencode auth login -p anthropic        # Specific provider
opencode auth list                      # List authenticated
opencode auth logout                    # Clear credentials
```

## Models

```bash
opencode models                         # List all
opencode models --refresh               # Refresh cache
opencode models anthropic               # Filter by provider
opencode models --verbose               # Include costs/metadata
```

## MCP Management

```bash
opencode mcp add                        # Interactive setup
opencode mcp list                       # List + status
opencode mcp auth <name>                # OAuth authenticate
opencode mcp logout <name>              # Remove credentials
opencode mcp debug <name>               # Diagnose issues
```

## Plugin Management

```bash
opencode plugin <module>                # Project scope
opencode plugin -g <module>             # Global scope
opencode plugin -f <module>             # Force replace
```

## Agent Management

```bash
opencode agent create                   # Interactive creation
opencode agent list                     # List all
```

## Session (CLI)

```bash
opencode session list
opencode session delete <id>
opencode --continue                     # Continue last session (TUI)
opencode --session <id>                 # Continue specific (TUI)
opencode --session <id> --fork          # Fork then continue (TUI)
```

## Stats & Export

```bash
opencode stats                          # Token usage
opencode stats --days 30                # Last 30 days
opencode stats --tools 10               # Top tools
opencode stats --models 5               # Top models
opencode export [sessionID]             # Export as JSON
opencode export --sanitize              # Redact sensitive data
opencode import <file|url>              # Import session
```

## Non-Interactive (alternative to HTTP)

```bash
opencode run "Explain closures"                       # One-shot
opencode run --model anthropic/claude-sonnet-4-5 "..."  # With model
opencode run --agent plan "Review for issues"          # With agent
opencode run -f file.ts "Add error handling"           # Attach file
opencode run --command "test"                          # Run slash command
opencode run --attach http://localhost:4096 "..."       # Attach to server
```
