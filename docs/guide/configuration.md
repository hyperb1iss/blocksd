# Configuration

blocksd uses a TOML configuration file for daemon settings. Everything works out of the box with sensible defaults, so configuration is entirely optional. Use it to disable the web UI or change the socket path. Discovery and keepalive timing fields are currently parsed but are not connected to the runtime.

## Config File Location

blocksd checks two paths on startup, in order of priority:

| Priority | Path                            | Typical Use          |
| -------- | ------------------------------- | -------------------- |
| 1        | `~/.config/blocksd/config.toml` | Per-user settings    |
| 2        | `/etc/blocksd/config.toml`      | System-wide defaults |

Only the first existing file is loaded; user and system settings are not merged. A missing explicit path falls back to normal discovery. You can pass an explicit path with `--config`:

```bash
blocksd run --config /path/to/config.toml
```

## Example Configuration

All settings live under a `[daemon]` section. Here's a fully annotated example showing every field at its default value:

```toml
[daemon]
# Parsed timing fields (currently not applied to the runtime)
scan_interval = 1.5            # seconds between MIDI port scans
ping_interval_master = 0.4     # keepalive ping to USB master (seconds)
ping_interval_dna = 1.666      # keepalive ping to DNA-connected blocks (seconds)
api_ping_timeout = 6.0         # seconds before declaring a device dead

# Logging
verbose = false                # true = debug logging (same as -v flag)

# Unix socket API
api_enabled = true             # start the socket API server
api_socket = ""                # empty = $XDG_RUNTIME_DIR/blocksd/blocksd.sock

# Web dashboard
web_enabled = true             # start HTTP + WebSocket server
web_host = "127.0.0.1"        # bind address
web_port = 9010                # HTTP / WebSocket port
```

## Settings Reference

### Device Discovery

The schema accepts `scan_interval`, `ping_interval_master`, `ping_interval_dna`, and `api_ping_timeout`, but the daemon does not pass these values into the topology runtime. Changing them currently has no effect. Runtime constants use 1.5-second scans, 400ms master pings, 1666ms DNA pings, and a 6-second host ACK timeout. The firmware's separate API mode timeout is 5 seconds.

### Logging

**`verbose`** enables debug-level logging, which includes protocol-level details like SysEx packet traces. Equivalent to passing `-v` on the command line. The CLI flag overrides this setting.

### Unix Socket API

**`api_enabled`** controls whether the Unix socket server starts with the daemon. When enabled, external clients can connect to discover devices, stream LED frames, and subscribe to touch/button events.

**`api_socket`** overrides the socket path. By default, blocksd creates the socket at `$XDG_RUNTIME_DIR/blocksd/blocksd.sock`, falling back to `/tmp/blocksd/blocksd.sock` if `XDG_RUNTIME_DIR` is not set.

### Web Dashboard

**`web_enabled`** starts the HTTP and WebSocket servers alongside the daemon. Defaults to `true`, so `blocksd run` serves the web UI unless disabled. Use `--no-browser` on `blocksd ui` if you just want the server without opening a browser window.

**`web_host`** and **`web_port`** control the server binding. The default `127.0.0.1:9010` only accepts local connections.

::: warning
Setting `web_host` to `0.0.0.0` exposes your device controls to the entire network. There is no authentication layer.
:::

## Command-Line Overrides

The `-v` flag enables verbose logging in addition to the config value. The `ui` command always enables the web server and replaces the configured host and port with its CLI values (including defaults):

```bash
blocksd run -v                   # enable debug logging
blocksd ui --port 8080           # override web port
blocksd ui --host 0.0.0.0       # bind to all interfaces
blocksd ui --no-browser          # start server without opening browser
```

## Environment Variables

blocksd respects standard Linux environment variables for path resolution:

| Variable          | Default | Used For              |
| ----------------- | ------- | --------------------- |
| `XDG_RUNTIME_DIR` | `/tmp`  | Unix socket directory |
