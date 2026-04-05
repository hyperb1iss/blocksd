# Troubleshooting

Common issues and how to fix them. If your problem isn't here, check the [GitHub issues](https://github.com/hyperb1iss/blocksd/issues) or file a new one.

## Device Not Detected

**Symptom**: `blocksd status` shows no MIDI ports.

**Check USB connection**:

```bash
lsusb | grep 2af4
```

If the device appears in `lsusb` but not in `blocksd status`, the issue is MIDI port naming.

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

**Is the daemon running?** LED commands connect to the running daemon via Unix socket. Start the daemon first:

```bash
blocksd run
```

**Is it a Lightpad?** Only Lightpad Block and Lightpad Block M support LED bitmap control. Other devices like LUMI Keys don't have an addressable LED grid.

**Check the socket**:

```bash
ls -la /tmp/blocksd/blocksd.sock
# or
ls -la $XDG_RUNTIME_DIR/blocksd/blocksd.sock
```

## High CPU Usage

**Symptom**: blocksd using more CPU than expected.

The daemon should idle near 0% CPU when devices are connected and stable. High CPU usually means:

- **Rapid reconnect loop**: a device is repeatedly connecting and disconnecting. Check `blocksd run -v` for rapid serial request cycles. This can happen with a damaged USB cable.
- **Scan interval too low**: if you've set `scan_interval` below 0.5 seconds, the MIDI port polling may be consuming CPU.

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

**Symptom**: `blocksd ui` starts but the browser shows a connection error.

**Check if the port is in use**:

```bash
ss -tlnp | grep 9010
```

Try a different port:

```bash
blocksd ui --port 8080
```

**Check firewall**: if accessing from another machine, ensure the port is open. By default, the web server only binds to `127.0.0.1` (localhost).

## Filing a Bug Report

If you can't resolve the issue, please file a bug at [github.com/hyperb1iss/blocksd/issues](https://github.com/hyperb1iss/blocksd/issues) with:

1. Output of `blocksd status --probe`
2. Daemon logs with verbose mode: `blocksd run -v`
3. Your Linux distribution and kernel version
4. Device type and firmware version (if known)
