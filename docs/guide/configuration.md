# Configuration

blocksd uses a TOML configuration file for daemon settings. Everything works out of the box with sensible defaults, so configuration is entirely optional. Tweak it when you want to tune scan timing, disable the web UI, or change the socket path.

## Config File Location

blocksd checks two paths on startup, in order of priority:

| Priority | Path                            | Typical Use          |
| -------- | ------------------------------- | -------------------- |
| 1        | `~/.config/blocksd/config.toml` | Per-user settings    |
| 2        | `/etc/blocksd/config.toml`      | System-wide defaults |

You can also pass an explicit path with `--config`:

```bash
blocksd run --config /path/to/config.toml
```

## Example Configuration

All settings live under a `[daemon]` section. Here's a fully annotated example showing every field at its default value:

```toml
[daemon]
# Device discovery
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

**`scan_interval`** controls how often the topology manager polls for new MIDI ports. The default of 1.5 seconds balances responsiveness against CPU usage. Lower values detect hot-plugged devices faster but increase polling overhead.

**`ping_interval_master`** and **`ping_interval_dna`** set the keepalive intervals. The master block (USB-connected) gets pinged every 400ms; DNA-connected blocks get pinged every 1.666 seconds. These defaults match the intervals used by ROLI's own drivers.

**`api_ping_timeout`** is the daemon's own timeout for declaring a device dead. The device firmware times out at 5 seconds, but blocksd waits 6 seconds before tearing down state, giving a small buffer for delayed ACKs.

::: tip
You rarely need to change the ping settings. The defaults were reverse-engineered from ROLI's C++ implementation and match the timing that keeps devices happiest.
:::

### Logging

**`verbose`** enables debug-level logging, which includes protocol-level details like SysEx packet traces. Equivalent to passing `-v` on the command line. The CLI flag overrides this setting.

### Unix Socket API

**`api_enabled`** controls whether the Unix socket server starts with the daemon. When enabled, external clients can connect to discover devices, stream LED frames, and subscribe to touch/button events.

**`api_socket`** overrides the socket path. By default, blocksd creates the socket at `$XDG_RUNTIME_DIR/blocksd/blocksd.sock`, falling back to `/tmp/blocksd/blocksd.sock` if `XDG_RUNTIME_DIR` is not set.

### Web Dashboard

**`web_enabled`** starts the HTTP and WebSocket servers alongside the daemon. Defaults to `true`, so `blocksd run` always serves the web UI. Use `--no-browser` on `blocksd ui` if you just want the server without opening a browser window.

**`web_host`** and **`web_port`** control the server binding. The default `127.0.0.1:9010` only accepts local connections.

::: warning
Setting `web_host` to `0.0.0.0` exposes your device controls to the entire network. There is no authentication layer.
:::

## Command-Line Overrides

CLI flags take precedence over the config file:

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
