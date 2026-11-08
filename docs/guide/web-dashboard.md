# Controller Dashboard

The dashboard configures your ROLI hardware and saves setups for the next session. Your DAW or synthesizer handles sound generation.

## Open the dashboard

Start the service or run `blocksd run`, then open the existing dashboard:

```bash
blocksd ui
blocksd ui --no-browser          # print the daemon's dashboard URL
```

The default address is `http://localhost:9010`. The `ui` command connects to the running daemon; it does not start another MIDI session. Set `web_host` and `web_port` in the daemon configuration to change the address.

## Devices

Select a connected device to see its battery, firmware, supported settings, and surface illustration. Lightpad touch events appear on the surface preview when the device sends them. The illustration is not an LED readback or a musical MIDI monitor.

Settings come from the daemon's shared metadata and device-reported ranges. MIDI modes use selectors, boolean settings use switches, and numeric settings use explicit value entry. An unavailable range leaves a setting read-only. The dashboard does not guess which settings a device program supports.

After changing a setting, wait for device confirmation. A successful send remains pending until the device reports the requested value. A disconnect, rejected value, or missing readback is shown as an error. Saving a preset captures reported values rather than an unconfirmed edit.

Connection details live in a disclosure below the workspace.

## Presets

Save a named snapshot from a device's settings panel. Only writable settings with valid reported values are saved; the dashboard reports any excluded settings. The presets page lists saved setups, including those belonging to disconnected devices.

- **Apply** sends a snapshot to its original device and waits for setting readback.
- **Restore on USB reconnect** selects the preset for the next USB connection or daemon start. Enabling it does not immediately change settings. Only one preset per device can be selected.
- **Export** downloads a JSON file; **import** validates that file and creates a separate preset. Imported presets have automatic restoration disabled.
- **Delete** removes the saved snapshot without changing the device's current settings.

Presets belong to the exact device serial and family. Application validates every setting against current reported ranges before sending the first write. If a MIDI send fails partway through, some settings may already have changed; refresh and inspect the device before retrying.

Automatic restoration waits for all saved settings to have reported ranges. The daemon attempts restoration once per USB connection and logs send failures. Brief topology dropouts within that connection preserve unsaved edits; detaching a DNA-connected block alone does not re-arm restoration. Confirm resulting values in the device settings; saved presets do not establish physical device compatibility.

## Storage and upgrades

On Linux, presets live in `$XDG_CONFIG_HOME/blocksd/presets.json`, defaulting to `~/.config/blocksd/presets.json`. Under systemd, blocksd uses the managed `CONFIGURATION_DIRECTORY`. On macOS, presets live in `~/Library/Application Support/blocksd/presets.json`.

Re-run `blocksd install --no-udev` after upgrading an existing Linux service to install its writable configuration directory. The installer restarts the service. Export important presets before changing installations. If the preset file cannot be read, the daemon keeps devices connected but disables preset operations and logs the file error; the original file is left untouched.

The HTTP server serves the bundled React app; WebSocket carries device events and requests. Browser WebSocket connections must use the dashboard's own origin. Native API clients may omit Origin; this is not network authentication. See the [API reference](../reference/api) for the protocol.
