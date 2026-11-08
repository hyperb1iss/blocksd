# Troubleshooting

Common issues and how to fix them. If your problem isn't here, check the [GitHub issues](https://github.com/hyperb1iss/blocksd/issues) or file a new one.

## Device Not Detected

**Symptom**: `blocksd status` shows no MIDI ports.

**Check USB connection**:

```bash
lsusb | grep 2af4
```

If the device appears in `lsusb` but not in `blocksd status`, check ALSA driver binding, permissions, and MIDI port naming.

**Check MIDI ports directly**:

```bash
arecordmidi -l
aplaymidi -l
```

Look for ports containing "BLOCK" or "Block". If none appear, the ALSA MIDI driver may not be loaded:

```bash
sudo modprobe snd-usb-audio
```

**Check udev rules**:

```bash
cat /etc/udev/rules.d/99-roli-blocks.rules
```

If the file is missing, run `blocksd install` to set up udev rules.

## Device Shows "Searching" Animation

**Symptom**: the Lightpad shows the searching dot animation even though blocksd is running.

This means blocksd hasn't successfully activated API mode. Check the daemon logs:

```bash
journalctl --user -u blocksd -f
# or if running in foreground:
blocksd run -v
```

Common causes:

- **Serial timeout**: the device isn't responding to serial dump requests. Try unplugging and replugging.
- **Another process holds the MIDI port**: check with `fuser /dev/snd/midi*` or look for other MIDI applications.
- **Permission denied**: the udev rules aren't applied. Run `blocksd install` and replug the device.

## LED Commands Do Nothing

**Symptom**: `blocksd led solid '#ff00ff'` returns but the Lightpad doesn't change.

**Check renderer startup.** The first frame uploads a renderer, then waits for complete code acknowledgement and a matching execution challenge reply before sending pixels. An accepted API frame can still be queued during startup. Check verbose logs for renderer initialisation or device errors, and see [LittleFoot status](./architecture/littlefoot) for tested firmware.

The LED CLI sends frames through the running daemon and exits. Check `blocksd status` before sending a frame.

**Use the matching lighting surface.** Lightpad Block and Lightpad Block M accept bitmap frames. LUMI Keys uses `blocksd led keys` or JSON `key_frame` and requires firmware 1.3.0 or newer.

**Check the socket**:

```bash
ls -la /tmp/blocksd/blocksd.sock
# or
ls -la $XDG_RUNTIME_DIR/blocksd/blocksd.sock
```

## Only Part of the Lightpad Animates

A stripe or moving upper rows with a frozen lower section can indicate an older heap streamer that repeatedly replaces an unfinished frame. Update to a build that completes transfer snapshots. If every row moves but the lower rows lag, use the buffered Lightpad renderer described in [Whole Lightpad Frames](./architecture/littlefoot#whole-lightpad-frames).

API acceptance measures queuing, so successful frame replies alone do not rule out either problem. A static corner pattern can help distinguish orientation or mapping errors from partial animation updates.

## High CPU Usage

**Symptom**: blocksd using more CPU than expected.

The daemon should idle near 0% CPU when devices are connected and stable. High CPU usually means:

- **Rapid reconnect loop**: a device is repeatedly connecting and disconnecting. Check `blocksd run -v` for rapid serial request cycles. This can happen with a damaged USB cable.
- **Concurrent hardware sessions**: run only one daemon. The LED/config CLI, `status --probe`, and `ui` connect to that daemon. The TOML timing fields currently have no runtime effect.

## Device Disconnects After 5 Seconds

**Symptom**: device connects, then disconnects after exactly 5 seconds.

The 5-second timeout is the API mode ping timeout. If blocksd fails to send pings in time, the device exits API mode. This shouldn't happen in normal operation, but can occur if:

- The asyncio event loop is blocked by a slow operation
- The system is under heavy load and ping tasks are being delayed
- There's a bug in the keepalive logic (please file an issue)

## MIDI Port Conflicts

**Symptom**: blocksd and your DAW can't both access the device.

ALSA supports multi-client MIDI natively, so blocksd and DAWs should coexist without conflict. If you're experiencing issues:

- Make sure you're using ALSA MIDI, not raw USB MIDI
- Some DAWs use exclusive access mode. Check your DAW's MIDI settings.
- PipeWire's MIDI bridge may behave differently. Check `pw-jack` configuration.

## systemd Service Issues

**Check service status**:

```bash
systemctl --user status blocksd
```

**View full logs**:

```bash
journalctl --user -u blocksd --no-pager -n 50
```

**Restart the service**:

```bash
systemctl --user restart blocksd
```

**Re-install if the service file is corrupted**:

```bash
blocksd uninstall
blocksd install
```

## Web Dashboard Won't Open

The `ui` command connects to the daemon and opens its reported address. If it cannot connect, start the service and check its logs:

```bash
systemctl --user start blocksd
journalctl --user -u blocksd --no-pager -n 30
blocksd ui --no-browser
```

For a custom socket, pass `blocksd --socket /path/to/blocksd.sock ui`. If the daemon reports no dashboard, enable `web_enabled` in its configuration and restart the service.

**Check firewall**: if accessing from another machine, ensure the port is open. By default, the web server only binds to `127.0.0.1` (localhost).

## Filing a Bug Report

If you can't resolve the issue, please file a bug at [github.com/hyperb1iss/blocksd/issues](https://github.com/hyperb1iss/blocksd/issues) with:

1. Output of `blocksd status --probe`
2. Daemon logs with verbose mode: `blocksd run -v`
3. Your Linux distribution and kernel version
4. Device type and firmware version (if known)
