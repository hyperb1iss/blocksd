---
layout: home

hero:
  name: blocksd
  text: ROLI Blocks without ROLI's apps
  tagline: "ROLI Blocks host protocol, implemented from reference code. Topology discovery, keepalive, LED streaming, pressure-sensitive touch, device configuration. Linux and macOS, with a Windows preview."
  actions:
    - theme: brand
      text: Get Started
      link: /guide/
    - theme: alt
      text: View on GitHub
      link: https://github.com/hyperb1iss/blocksd

features:
  - icon: 🔌
    title: API Mode Keepalive
    details: Periodic pings prevent the 5-second device timeout. Blocks stay in API mode indefinitely, no more searching animations.
  - icon: 🏗️
    title: Topology Management
    details: Auto-discovers devices over USB, tracks DNA-connected blocks through master. Full mesh networking awareness.
  - icon: 💡
    title: LED Control
    details: 15x15 RGB grid on Lightpad Block / M and per-key colors on LUMI Keys. CLI patterns and binary frame streaming.
  - icon: 👆
    title: Touch & Button Events
    details: Normalized pressure-sensitive touch data (x, y, z, velocity) and button callbacks over Unix socket and WebSocket.
  - icon: ⚙️
    title: Device Configuration
    details: Read and write device settings like velocity sensitivity, MIDI channel, scale mode, and more via CLI or API.
  - icon: 🛡️
    title: Background Service
    details: "A systemd user service with watchdog heartbeat and udev rules on Linux, or a LaunchAgent on macOS. Install with one command."
---

<style>
:root {
  --vp-home-hero-name-color: transparent;
  --vp-home-hero-name-background: linear-gradient(135deg, #e135ff 0%, #80ffea 100%);
}

.dark {
  --vp-home-hero-image-background-image: linear-gradient(135deg, rgba(225, 53, 255, 0.2) 0%, rgba(128, 255, 234, 0.2) 100%);
  --vp-home-hero-image-filter: blur(56px);
}
</style>
