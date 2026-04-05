import { defineConfig } from "vitepress";

export default defineConfig({
  title: "blocksd",
  description: "Linux Daemon for ROLI Blocks Devices",
  base: "/blocksd/",
  lastUpdated: true,

  head: [
    ["meta", { name: "theme-color", content: "#e135ff" }],
    ["meta", { property: "og:type", content: "website" }],
    ["meta", { property: "og:title", content: "blocksd Documentation" }],
    [
      "meta",
      {
        property: "og:description",
        content: "Linux Daemon for ROLI Blocks Devices",
      },
    ],
    ["meta", { property: "og:site_name", content: "blocksd" }],
    ["meta", { name: "twitter:card", content: "summary" }],
  ],

  themeConfig: {
    nav: [
      { text: "Guide", link: "/guide/" },
      {
        text: "Reference",
        items: [
          { text: "CLI Commands", link: "/reference/cli" },
          { text: "External API", link: "/reference/api" },
          { text: "Supported Devices", link: "/reference/devices" },
        ],
      },
      { text: "Protocol", link: "/protocol/" },
      { text: "Architecture", link: "/architecture/" },
      { text: "Troubleshooting", link: "/troubleshooting" },
    ],

    sidebar: {
      "/guide/": [
        {
          text: "Getting Started",
          items: [
            { text: "Introduction", link: "/guide/" },
            { text: "Installation", link: "/guide/installation" },
            { text: "Quick Start", link: "/guide/quick-start" },
            { text: "Configuration", link: "/guide/configuration" },
            { text: "Web Dashboard", link: "/guide/web-dashboard" },
          ],
        },
      ],
      "/reference/": [
        {
          text: "Reference",
          items: [
            { text: "CLI Commands", link: "/reference/cli" },
            { text: "External API", link: "/reference/api" },
            { text: "Supported Devices", link: "/reference/devices" },
          ],
        },
      ],
      "/protocol/": [
        {
          text: "ROLI Blocks Protocol",
          items: [
            { text: "Overview", link: "/protocol/" },
            { text: "SysEx Framing", link: "/protocol/sysex-framing" },
            { text: "Message Types", link: "/protocol/messages" },
            { text: "Topology", link: "/protocol/topology" },
            { text: "Connection Lifecycle", link: "/protocol/lifecycle" },
          ],
        },
      ],
      "/architecture/": [
        {
          text: "Architecture",
          items: [
            { text: "Overview", link: "/architecture/" },
            { text: "Module Structure", link: "/architecture/modules" },
            { text: "Data Flow", link: "/architecture/data-flow" },
            { text: "LittleFoot VM", link: "/architecture/littlefoot" },
          ],
        },
      ],
    },

    editLink: {
      pattern: "https://github.com/hyperb1iss/blocksd/edit/main/docs/:path",
      text: "Edit this page on GitHub",
    },

    socialLinks: [
      { icon: "github", link: "https://github.com/hyperb1iss/blocksd" },
    ],

    footer: {
      message: "Released under the ISC License.",
      copyright: "Copyright \u00a9 2026 Stefanie Jane",
    },

    search: {
      provider: "local",
    },
  },

  markdown: {
    theme: {
      light: "github-light",
      dark: "one-dark-pro",
    },
  },
});
