#!/usr/bin/env python3
"""
OpenCode HTTP API CLI wrapper.

Delegates all operations to an `opencode serve` instance via HTTP.
In managed mode, transparently spawns and maintains the server process.

Usage:
  python main.py ask "<prompt>" [--model p/m] [--agent a] [--dir d]
  python main.py fire "<prompt>" [--model p/m] [--agent a] [--dir d]
  python main.py check <session-id>
  python main.py todo <session-id>
  python main.py diffs <session-id>
  python main.py conversation <session-id>
  python main.py session list
  python main.py session get <id>
  python main.py session delete <id>
  python main.py session fork <id> [--message-id m]
  python main.py session abort <id>
  python main.py read <path>
  python main.py ls <path>
  python main.py find "<pattern>"
  python main.py find-file "<name>"
  python main.py find-symbol "<name>"
  python main.py config
  python main.py config-set '<json>'
  python main.py providers
  python main.py agents
  python main.py mcp-status
  python main.py mcp-add <name> '<json>'
  python main.py restart
  python main.py status

Config file: opencode-config.json (same directory as this script)
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' library not found. Install it with: pip install requests")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "opencode-config.json"
PID_FILE = SCRIPT_DIR / ".opencode-server.pid"

# ── config ──────────────────────────────────────────────────────────────

def load_config():
    if not CONFIG_PATH.exists():
        print(f"Error: Config file not found at {CONFIG_PATH}")
        print()
        print("Create it with the following structure:")
        print(json.dumps({
            "mode": "managed",
            "url": "http://127.0.0.1:4096",
            "password": None,
            "username": "opencode",
            "port": 4096,
            "hostname": "127.0.0.1",
            "default_provider": None,
            "default_model": None,
        }, indent=2))
        print()
        print("Available modes:")
        print("  managed  — This script spawns and manages the opencode serve process.")
        print("  external — You provide the URL of an already-running opencode serve.")
        sys.exit(1)

    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    required = ["mode", "url"]
    for k in required:
        if k not in cfg:
            print(f"Error: '{k}' missing from {CONFIG_PATH}")
            sys.exit(1)

    if cfg["mode"] not in ("managed", "external"):
        print(f"Error: mode must be 'managed' or 'external', got '{cfg['mode']}'")
        sys.exit(1)

    url = cfg["url"].rstrip("/")
    cfg["url"] = url
    cfg.setdefault("password", None)
    cfg.setdefault("username", "opencode")
    cfg.setdefault("port", 4096)
    cfg.setdefault("hostname", "127.0.0.1")
    cfg.setdefault("default_provider", None)
    cfg.setdefault("default_model", None)
    return cfg


def auth_header(cfg):
    if cfg["password"]:
        from base64 import b64encode
        raw = f"{cfg['username']}:{cfg['password']}"
        return {"Authorization": "Basic " + b64encode(raw.encode()).decode()}
    return {}


def base_headers(cfg, extra=None):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    h.update(auth_header(cfg))
    if extra:
        h.update(extra)
    return h


# ── server lifecycle (managed only) ─────────────────────────────────────

def is_running(cfg):
    try:
        r = requests.get(f"{cfg['url']}/global/health",
                         headers=auth_header(cfg), timeout=5)
        return r.status_code == 200 and r.json().get("healthy", False)
    except Exception:
        return False


def read_pid():
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except Exception:
            return None
    return None


def write_pid(pid):
    PID_FILE.write_text(str(pid))


def find_opencode_binary():
    candidates = ["opencode"]
    # On Windows, also try common install locations
    if sys.platform == "win32":
        import shutil
        for p in [
            r"C:\Program Files\opencode\opencode.exe",
            r"C:\Program Files (x86)\opencode\opencode.exe",
        ]:
            candidates.append(p)
        found = shutil.which("opencode.exe")
        if found:
            return found

    import shutil
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    return None


def kill_process():
    pid = read_pid()
    if pid is None:
        return

    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass

    # Also try pkill as fallback
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/IM", "opencode.exe", "/F"],
                           capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "opencode serve"],
                           capture_output=True)
    except Exception:
        pass

    time.sleep(0.5)
    PID_FILE.unlink(missing_ok=True)


def spawn_server(cfg):
    binary = find_opencode_binary()
    if not binary:
        print("Error: 'opencode' binary not found on PATH.")
        print("Install it: curl -fsSL https://opencode.ai/install | bash")
        sys.exit(1)

    port = cfg.get("port", 4096)
    hostname = cfg.get("hostname", "127.0.0.1")
    args = [binary, "serve", "--port", str(port)]
    if hostname not in ("127.0.0.1", "localhost"):
        args.extend(["--hostname", hostname])

    env = os.environ.copy()
    if cfg.get("password"):
        env["OPENCODE_SERVER_PASSWORD"] = cfg["password"]

    if sys.platform == "win32":
        p = subprocess.Popen(args, env=env,
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    else:
        p = subprocess.Popen(args, env=env,
                             start_new_session=True,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

    write_pid(p.pid)

    # Poll until healthy
    deadline = time.time() + 30
    while time.time() < deadline:
        if is_running(cfg):
            return True
        if p.poll() is not None:
            print("Error: opencode serve exited immediately.")
            sys.exit(1)
        time.sleep(0.5)

    print("Error: opencode serve did not become healthy within 30 seconds.")
    kill_process()
    sys.exit(1)


def ensure_running(cfg):
    if is_running(cfg):
        return
    if cfg["mode"] == "external":
        print(f"Error: OpenCode server not reachable at {cfg['url']}")
        print("Make sure 'opencode serve' is running, or switch to managed mode.")
        sys.exit(1)
    spawn_server(cfg)


def restart_server(cfg):
    if cfg["mode"] == "external":
        print("Error: Cannot restart an external server. Restart opencode serve manually.")
        sys.exit(1)

    print("Restarting opencode serve...")
    kill_process()
    spawn_server(cfg)
    print("Server restarted and healthy.")


# ── HTTP helpers ─────────────────────────────────────────────────────────

def http_get(cfg, path, **kwargs):
    ensure_running(cfg)
    h = base_headers(cfg)
    params = kwargs.pop("params", {})
    d = kwargs.pop("directory", None)
    if d:
        h["x-opencode-directory"] = d
    r = requests.get(f"{cfg['url']}{path}", headers=h, params=params, timeout=kwargs.pop("timeout", 120), **kwargs)
    r.raise_for_status()
    if r.status_code == 204:
        return None
    return r.json()


def http_post(cfg, path, body=None, **kwargs):
    ensure_running(cfg)
    h = base_headers(cfg)
    d = kwargs.pop("directory", None)
    if d:
        h["x-opencode-directory"] = d
    r = requests.post(f"{cfg['url']}{path}", headers=h,
                      data=json.dumps(body) if body else None,
                      timeout=kwargs.pop("timeout", 600), **kwargs)
    r.raise_for_status()
    if r.status_code == 204:
        return None
    return r.json()


def http_delete(cfg, path, **kwargs):
    ensure_running(cfg)
    h = base_headers(cfg)
    d = kwargs.pop("directory", None)
    if d:
        h["x-opencode-directory"] = d
    r = requests.delete(f"{cfg['url']}{path}", headers=h, timeout=kwargs.pop("timeout", 30), **kwargs)
    r.raise_for_status()
    if r.status_code == 204:
        return None
    return r.json()


def http_patch(cfg, path, body=None, **kwargs):
    ensure_running(cfg)
    h = base_headers(cfg)
    d = kwargs.pop("directory", None)
    if d:
        h["x-opencode-directory"] = d
    r = requests.patch(f"{cfg['url']}{path}", headers=h,
                       data=json.dumps(body) if body else None,
                       timeout=kwargs.pop("timeout", 30), **kwargs)
    r.raise_for_status()
    if r.status_code == 204:
        return None
    return r.json()


# ── helpers ──────────────────────────────────────────────────────────────

def parse_model(model_str):
    """Parse 'provider/model' into {providerID, modelID}."""
    if not model_str:
        return None
    parts = model_str.split("/", 1)
    if len(parts) == 2:
        return {"providerID": parts[0], "modelID": parts[1]}
    return {"modelID": model_str}


def resolve_model(cfg, model_str):
    m = parse_model(model_str)
    if m:
        return m
    if cfg.get("default_provider") and cfg.get("default_model"):
        return {"providerID": cfg["default_provider"], "modelID": cfg["default_model"]}
    return None


def build_message_body(prompt, model=None, agent=None):
    body = {"parts": [{"type": "text", "text": prompt}]}
    if model:
        body["model"] = model
    if agent:
        body["agent"] = agent
    return body


def fmt_json(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _fmt_age(seconds):
    if seconds < 0:
        return "0s"
    if seconds < 60:
        return f"{int(seconds)}s"
    mins = int(seconds / 60)
    if mins < 60:
        return f"{mins}m"
    hours = mins / 60
    if hours < 24:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"


def resolve_session_status(statuses, sid):
    s = statuses.get(sid)
    if isinstance(s, str):
        return s
    if isinstance(s, dict):
        return s.get("type", "unknown")
    return "unknown"


# ── commands ─────────────────────────────────────────────────────────────

def cmd_status(cfg):
    ensure_running(cfg)
    try:
        health = http_get(cfg, "/global/health", timeout=5)
        print(f"Server: healthy (v{health.get('version', '?')})")
    except Exception as e:
        print(f"Server: UNREACHABLE — {e}")
        sys.exit(1)


def cmd_ask(cfg, prompt, model_str=None, agent=None, directory=None, sid=None):
    m = resolve_model(cfg, model_str)
    if sid:
        target_sid = sid
    else:
        session = http_post(cfg, "/session", {"title": prompt[:80]}, directory=directory)
        target_sid = session["id"]
    body = build_message_body(prompt, m, agent)
    try:
        resp = http_post(cfg, f"/session/{target_sid}/message", body, directory=directory, timeout=600)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    parts = resp.get("parts", [])
    for part in parts:
        if part.get("type") == "text":
            print(part.get("text", ""))


def cmd_fire(cfg, prompt, model_str=None, agent=None, directory=None, sid=None):
    m = resolve_model(cfg, model_str)
    if sid:
        target_sid = sid
    else:
        session = http_post(cfg, "/session", {"title": prompt[:80]}, directory=directory)
        target_sid = session["id"]
    body = build_message_body(prompt, m, agent)
    http_post(cfg, f"/session/{target_sid}/prompt_async", body, directory=directory)
    print(target_sid)




def cmd_check(cfg, session_id):
    # session info
    try:
        info = http_get(cfg, f"/session/{session_id}")
        title = info.get("title") or info.get("slug") or session_id[:12]
        agent = info.get("agent", "?")
        model = info.get("model", {})
        model_id = model.get("id", "?") if isinstance(model, dict) else str(model)
        t = info.get("time", {})
        created = t.get("created", 0)
        updated = t.get("updated", 0)
        now = time.time() * 1000
        age = (now - created) / 1000
        last = (now - updated) / 1000
        print(f"Title: {title}")
        print(f"Agent: {agent}  |  Model: {model_id}")
        print(f"Created: {_fmt_age(age)} ago  |  Updated: {_fmt_age(last)} ago")
    except Exception:
        print(f"Session: {session_id}")

    # status
    try:
        statuses = http_get(cfg, "/session/status")
        status = resolve_session_status(statuses, session_id)
        print(f"Status: {status}")
    except Exception:
        pass

    # todo
    try:
        todos = http_get(cfg, f"/session/{session_id}/todo")
        if todos and isinstance(todos, list) and len(todos) > 0:
            completed = sum(1 for t in todos if t.get("status") == "completed")
            in_prog = sum(1 for t in todos if t.get("status") == "in_progress")
            print(f"Tasks: {completed}/{len(todos)} completed, {in_prog} in progress")
            for t in todos:
                if t.get("status") == "in_progress":
                    print(f"  Current: {t.get('content', t.get('title', '?'))}")
    except Exception:
        pass

    # diffs
    try:
        diffs = http_get(cfg, f"/session/{session_id}/diff")
        if diffs and isinstance(diffs, list) and len(diffs) > 0:
            print(f"Files changed: {len(diffs)}")
    except Exception:
        pass


def cmd_todo(cfg, session_id):
    todos = http_get(cfg, f"/session/{session_id}/todo")
    print(fmt_json(todos))


def cmd_diffs(cfg, session_id):
    diffs = http_get(cfg, f"/session/{session_id}/diff")
    print(fmt_json(diffs))


def cmd_conversation(cfg, session_id, limit=None, offset=0):
    msgs = http_get(cfg, f"/session/{session_id}/message")
    total = len(msgs) if msgs else 0

    if not msgs:
        print("(empty)")
        return

    if limit is None:
        limit = 20

    end_idx = min(offset + limit, total)
    shown_msgs = msgs[offset:end_idx]

    for msg in shown_msgs:
        info = msg.get("info", {})
        role = info.get("role", "?")
        parts = msg.get("parts", [])
        print(f"--- {role} ---")
        for part in parts:
            if part.get("type") == "text":
                print(part.get("text", ""))
            else:
                print(f"[{part.get('type')}]")
        print()

    if total > end_idx or offset > 0:
        print(f"[{len(shown_msgs)} messages shown (range {offset+1}-{end_idx} of {total}). "
              f"Use --limit/-l and --offset/-o for more]")


def cmd_session_list(cfg, directory=None):
    sessions = http_get(cfg, "/session", directory=directory)
    if not sessions:
        print("No sessions.")
        return
    statuses = http_get(cfg, "/session/status", directory=directory)
    now_ms = time.time() * 1000
    for s in sessions:
        sid = s.get("id", "?")
        title = s.get("title") or s.get("slug") or sid[:12]
        status = resolve_session_status(statuses, sid)
        agent = s.get("agent", "?")
        model = s.get("model", {})
        model_id = model.get("id", "?") if isinstance(model, dict) else str(model)
        t = s.get("time", {})
        updated = t.get("updated", 0)
        last = (now_ms - updated) / 1000 if updated else 0
        print(f"[{status}] {title}  {sid}  {agent}  {model_id}  {_fmt_age(last)}")


def cmd_session_get(cfg, session_id, directory=None):
    s = http_get(cfg, f"/session/{session_id}", directory=directory)
    print(fmt_json(s))


def cmd_session_delete(cfg, session_id, directory=None):
    http_delete(cfg, f"/session/{session_id}", directory=directory)
    print(f"Session {session_id} deleted.")


def cmd_session_fork(cfg, session_id, message_id=None, directory=None):
    body = {}
    if message_id:
        body["messageID"] = message_id
    s = http_post(cfg, f"/session/{session_id}/fork", body, directory=directory)
    print(s.get("id", "?"))


def cmd_session_abort(cfg, session_id, directory=None):
    http_post(cfg, f"/session/{session_id}/abort", directory=directory)
    print(f"Session {session_id} aborted.")


def cmd_read(cfg, path_str, directory=None):
    content = http_get(cfg, "/file/content", params={"path": path_str}, directory=directory)
    if isinstance(content, dict):
        print(content.get("content", fmt_json(content)))
    else:
        print(content)


def cmd_ls(cfg, path_str, directory=None):
    entries = http_get(cfg, "/file", params={"path": path_str}, directory=directory)
    if isinstance(entries, list):
        for e in entries:
            name = e.get("name") or e.get("path") or str(e)
            etype = "DIR" if e.get("type") == "directory" else "FILE"
            print(f"[{etype}] {name}")
    else:
        print(entries)


def cmd_find(cfg, pattern, directory=None):
    results = http_get(cfg, "/find", params={"pattern": pattern}, directory=directory)
    print(fmt_json(results))


def cmd_find_file(cfg, name, directory=None):
    results = http_get(cfg, "/find/file", params={"query": name}, directory=directory)
    if isinstance(results, list):
        for r in results:
            print(r)
    else:
        print(results)


def cmd_find_symbol(cfg, name, directory=None):
    results = http_get(cfg, "/find/symbol", params={"query": name}, directory=directory)
    print(fmt_json(results))


def cmd_config(cfg, directory=None):
    c = http_get(cfg, "/config", directory=directory)
    print(fmt_json(c))


def cmd_config_set(cfg, json_str, directory=None):
    data = json.loads(json_str)
    http_patch(cfg, "/config", body=data, directory=directory)
    print("Config updated.")


def cmd_providers(cfg, directory=None, filter_str=None):
    p = http_get(cfg, "/provider", directory=directory)
    all_providers = p.get("all", []) if isinstance(p, dict) else p
    connected = p.get("connected", []) if isinstance(p, dict) else []

    if not isinstance(all_providers, list) or not isinstance(connected, list):
        print(fmt_json(p))
        return

    by_id = {pr["id"]: pr for pr in all_providers if isinstance(pr, dict) and "id" in pr}

    result = []
    for cid in connected:
        if isinstance(cid, str) and cid in by_id:
            result.append(by_id[cid])
        elif isinstance(cid, dict):
            result.append(cid)

    if not result:
        print("No connected providers found.")
        return

    if filter_str:
        lower = filter_str.lower()
        result = [pr for pr in result
                  if lower in (pr.get("id", "") + pr.get("name", "")).lower()]
        if not result:
            print(f"No providers matching '{filter_str}'.")
            return

    for pr in result:
        pid = pr.get("id") or pr.get("name", "?")
        print(f"[{pid}]")
        models = pr.get("models", [])
        if isinstance(models, dict):
            models = list(models.values())
        if isinstance(models, list) and len(models) > 0:
            for m in models:
                if isinstance(m, dict):
                    mid = m.get("id") or m.get("name", "?")
                    print(f"  - {mid}")
                else:
                    print(f"  - {m}")
        else:
            print("  (no models listed)")
        print()


def cmd_agents(cfg, directory=None):
    a = http_get(cfg, "/agent", directory=directory)
    print(fmt_json(a))


def cmd_mcp_status(cfg, directory=None):
    m = http_get(cfg, "/mcp", directory=directory)
    print(fmt_json(m))


def cmd_mcp_add(cfg, name, json_str, directory=None):
    config_data = json.loads(json_str)
    http_post(cfg, "/mcp", body={"name": name, "config": config_data}, directory=directory)
    print(f"MCP server '{name}' added.")


# ── main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="OpenCode HTTP API CLI wrapper",
        usage="python main.py <command> [args...]"
    )
    sub = parser.add_subparsers(dest="command")

    # ask
    p = sub.add_parser("ask", help="Send a prompt and print the response (blocks until done)")
    p.add_argument("prompt", help="Prompt text")
    p.add_argument("--model", "-m", help="Model as provider/model (e.g. anthropic/claude-sonnet-4-5)")
    p.add_argument("--agent", "-a", help="Agent name (e.g. build, plan)")
    p.add_argument("--sid", help="Send to existing session instead of creating new")
    p.add_argument("--dir", "-d", help="Target project directory")

    # fire
    p = sub.add_parser("fire", help="Dispatch a prompt asynchronously, print session ID")
    p.add_argument("prompt")
    p.add_argument("--model", "-m")
    p.add_argument("--agent", "-a")
    p.add_argument("--sid", help="Send to existing session instead of creating new")
    p.add_argument("--dir", "-d")

    # check
    p = sub.add_parser("check", help="Quick status of a session")
    p.add_argument("session_id")

    # todo
    p = sub.add_parser("todo", help="Get session todo list")
    p.add_argument("session_id")

    # diffs
    p = sub.add_parser("diffs", help="Get file diffs for a session")
    p.add_argument("session_id")

    # conversation
    p = sub.add_parser("conversation", help="Get conversation history")
    p.add_argument("session_id")
    p.add_argument("--limit", "-l", type=int, help="Max messages to show (default: 20)")
    p.add_argument("--offset", "-o", type=int, default=0, help="Skip first N messages")

    # session
    p = sub.add_parser("session", help="Session management")
    ssub = p.add_subparsers(dest="session_cmd")
    p = ssub.add_parser("list", help="List all sessions")
    p.add_argument("--dir", "-d")
    p = ssub.add_parser("get", help="Get session details")
    p.add_argument("id")
    p.add_argument("--dir", "-d")
    p = ssub.add_parser("delete", help="Delete a session")
    p.add_argument("id")
    p.add_argument("--dir", "-d")
    p = ssub.add_parser("fork", help="Fork a session")
    p.add_argument("id")
    p.add_argument("--message-id", help="Message ID to fork at")
    p.add_argument("--dir", "-d")
    p = ssub.add_parser("abort", help="Abort a running session")
    p.add_argument("id")
    p.add_argument("--dir", "-d")

    # read
    p = sub.add_parser("read", help="Read a file")
    p.add_argument("path")
    p.add_argument("--dir", "-d")

    # ls
    p = sub.add_parser("ls", help="List directory contents")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--dir", "-d")

    # find
    p = sub.add_parser("find", help="Search text/regex across project")
    p.add_argument("pattern")
    p.add_argument("--dir", "-d")

    # find-file
    p = sub.add_parser("find-file", help="Fuzzy file name search")
    p.add_argument("name")
    p.add_argument("--dir", "-d")

    # find-symbol
    p = sub.add_parser("find-symbol", help="Find workspace symbols")
    p.add_argument("name")
    p.add_argument("--dir", "-d")

    # config
    p = sub.add_parser("config", help="Get current config")
    p.add_argument("--dir", "-d")

    # config-set
    p = sub.add_parser("config-set", help="Update config (partial merge)")
    p.add_argument("json_str", help="JSON string or object")
    p.add_argument("--dir", "-d")

    # providers
    p = sub.add_parser("providers", help="List connected providers")
    p.add_argument("--filter", "-f", help="Filter by provider ID or name")
    p.add_argument("--dir", "-d")

    # agents
    p = sub.add_parser("agents", help="List agents")
    p.add_argument("--dir", "-d")

    # mcp-status
    p = sub.add_parser("mcp-status", help="MCP server status")
    p.add_argument("--dir", "-d")

    # mcp-add
    p = sub.add_parser("mcp-add", help="Add MCP server dynamically")
    p.add_argument("name")
    p.add_argument("config_json", help="MCP server config as JSON")
    p.add_argument("--dir", "-d")

    # restart
    sub.add_parser("restart", help="Restart opencode serve (managed mode only)")

    # status
    sub.add_parser("status", help="Check server health")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cfg = load_config()

    try:
        if args.command == "status":
            cmd_status(cfg)
        elif args.command == "restart":
            restart_server(cfg)
        elif args.command == "ask":
            cmd_ask(cfg, args.prompt, args.model, args.agent, args.dir, args.sid)
        elif args.command == "fire":
            cmd_fire(cfg, args.prompt, args.model, args.agent, args.dir, args.sid)
        elif args.command == "check":
            cmd_check(cfg, args.session_id)
        elif args.command == "todo":
            cmd_todo(cfg, args.session_id)
        elif args.command == "diffs":
            cmd_diffs(cfg, args.session_id)
        elif args.command == "conversation":
            cmd_conversation(cfg, args.session_id, args.limit, args.offset)
        elif args.command == "session":
            if args.session_cmd == "list":
                cmd_session_list(cfg, args.dir)
            elif args.session_cmd == "get":
                cmd_session_get(cfg, args.id, args.dir)
            elif args.session_cmd == "delete":
                cmd_session_delete(cfg, args.id, args.dir)
            elif args.session_cmd == "fork":
                cmd_session_fork(cfg, args.id, args.message_id, args.dir)
            elif args.session_cmd == "abort":
                cmd_session_abort(cfg, args.id, args.dir)
            else:
                print("Unknown session command. Use: list, get, delete, fork, abort")
                sys.exit(1)
        elif args.command == "read":
            cmd_read(cfg, args.path, args.dir)
        elif args.command == "ls":
            cmd_ls(cfg, args.path, args.dir)
        elif args.command == "find":
            cmd_find(cfg, args.pattern, args.dir)
        elif args.command == "find-file":
            cmd_find_file(cfg, args.name, args.dir)
        elif args.command == "find-symbol":
            cmd_find_symbol(cfg, args.name, args.dir)
        elif args.command == "config":
            cmd_config(cfg, args.dir)
        elif args.command == "config-set":
            cmd_config_set(cfg, args.json_str, args.dir)
        elif args.command == "providers":
            cmd_providers(cfg, args.dir, args.filter)
        elif args.command == "agents":
            cmd_agents(cfg, args.dir)
        elif args.command == "mcp-status":
            cmd_mcp_status(cfg, args.dir)
        elif args.command == "mcp-add":
            cmd_mcp_add(cfg, args.name, args.config_json, args.dir)
        else:
            parser.print_help()
            sys.exit(1)
    except requests.exceptions.HTTPError as e:
        resp = e.response
        try:
            body = resp.text[:1000]
        except Exception:
            body = "(no body)"
        print(f"HTTP {resp.status_code} {resp.request.method} {resp.request.url}")
        print(body)
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to {cfg['url']}")
        if cfg["mode"] == "external":
            print("Make sure 'opencode serve' is running, or switch to managed mode.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
