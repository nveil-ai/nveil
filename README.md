<p align="center">
  <img src="https://raw.githubusercontent.com/nveil-ai/nveil-toolkit/main/assets/logo.png" alt="NVEIL" width="180">
</p>

<h1 align="center">NVEIL — Community Edition</h1>

<p align="center">
  <strong>Chat with your data — explore, process, and visualize it, fast.</strong><br>
  The self-hosted, open-source edition of <a href="https://app.nveil.com">NVEIL</a>.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0--or--later-blue" alt="License"></a>
  <a href="https://github.com/nveil-ai/nveil/stargazers"><img src="https://img.shields.io/github/stars/nveil-ai/nveil?style=flat&color=yellow" alt="Stars"></a>
  <a href="https://github.com/nveil-ai/nveil/network/members"><img src="https://img.shields.io/github/forks/nveil-ai/nveil?style=flat" alt="Forks"></a>
  <a href="https://github.com/nveil-ai/nveil/releases"><img src="https://img.shields.io/github/v/release/nveil-ai/nveil?sort=semver" alt="Release"></a>
  <a href="https://github.com/nveil-ai/nveil/commits"><img src="https://img.shields.io/github/last-commit/nveil-ai/nveil" alt="Last commit"></a>
  <a href="https://discord.gg/3KdDwzT7rt"><img src="https://img.shields.io/badge/Discord-join-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://docs.nveil.com"><img src="https://img.shields.io/badge/docs-docs.nveil.com-blue" alt="Docs"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> &bull;
  <a href="#why-nveil">Why NVEIL</a> &bull;
  <a href="#use-it-from-your-code">From code</a> &bull;
  <a href="#community">Community</a> &bull;
  <a href="#contributing">Contributing</a> &bull;
  <a href="#license">License</a>
</p>

---

**NVEIL is the fast, conversational way to explore, process, and visualize data — any kind, any domain.** Point it at your data, say what you want in plain language, and NVEIL prepares it and turns it into interactive, production-ready visualizations. No plotting code, no dashboards to wire by hand.

This is the **Community Edition**: the complete platform, free and open under the AGPL, that you self-host. **Don't want to run your own server?** The same platform is available hosted at **[nveil.com](https://nveil.com)**, with a free tier plus paid plans, nothing to install.

<p align="center">
  <img src=".github/assets/hero.png" alt="NVEIL — conversational data exploration with an interactive 3D surface visualization" width="900">
</p>

<p align="center">
  <strong><a href="https://app.nveil.com">▶&nbsp; Try the live demo</a></strong> &nbsp;—&nbsp; no install, free to start.
</p>

## Quick start

Self-host in minutes with **prebuilt images** — nothing to build.

> **Prerequisites:** Docker + Docker Compose, and one LLM provider — a Gemini / OpenAI / Anthropic / Mistral key, or a local model (Ollama, llama.cpp, any OpenAI-compatible endpoint).

**1.** Download **[`docker-compose.yaml`](https://github.com/nveil-ai/nveil/raw/main/docker-compose.yaml)** into an empty folder — it's the only file you need.

**2.** Run the setup wizard, then open <http://localhost:3000> to configure (it writes your `.env`):

```bash
docker compose up setup
```

**3.** Pull the images and launch:

```bash
docker compose up -d
```

Open **https://localhost:8000** — and start chatting with your data. 🎉

## Developer setup

Want to **debug**, turn on **LLM tracing**, or **build the images yourself**? Clone the repo and use `docker-compose.dev.yml` — it builds from source, with live reload and TEST mode (debug routes):

```bash
git clone https://github.com/nveil-ai/nveil.git
cd nveil

docker compose -f docker-compose.dev.yml up setup                       # configure → localhost:3000
docker compose -f docker-compose.dev.yml --profile core up --build -d   # build & run → localhost:8000
```

Optional LLM tracing with the bundled Langfuse (→ <http://localhost:3030>):

```bash
docker compose -f docker-compose.dev.yml --profile core --profile tracing up -d
```

## Why NVEIL?

- 💬 **Conversational** — describe what you want in plain language; no plotting code, no manual dashboards.
- 🧮 **Explore *and* process** — clean, transform, aggregate, and join your data, not just chart it.
- 🌐 **Any data, any domain** — from a quick CSV to scientific datasets: business analytics, geospatial, 3D, imaging, signals, networks, and beyond.
- 🔒 **Private by design** — raw data stays on your infrastructure; only metadata reaches the AI.
- 🎯 **Deterministic** — visualizations come from constraint solving, not guesswork: same request → same result, every time.
- 🤖 **Bring your own model** — Gemini, OpenAI, Anthropic, Mistral, or a local model.
- 🗂️ **A real app** — chat, dashboards, file management, multi-user rooms, internationalization.

## Use it from your code

The web app is the main way to use NVEIL. To drive it **programmatically** — from a Python script, your terminal, or an AI agent — there's an optional client, the **NVEIL Toolkit**:

```bash
pip install nveil
```

A Python SDK, a `nveil` CLI, and an MCP server for agents (Claude Code, Cursor, …), all pointed at your NVEIL instance. See **[nveil-toolkit](https://github.com/nveil-ai/nveil-toolkit)**.

## Community

Questions, ideas, or want to show what you built? Join us:

- 💬 **[Discord](https://discord.gg/3KdDwzT7rt)** — chat with the team and other users.
- 🗣️ **[GitHub Discussions](https://github.com/nveil-ai/nveil/discussions)** — Q&A and proposals.
- 🐛 **[Issues](https://github.com/nveil-ai/nveil/issues)** — bug reports and feature requests.

## Contributing

Contributions are welcome — the developer setup above is all you need to get started.

Pull requests are accepted under the project's **[Contributor License Agreement](licensing/CLA.md)** — you sign it **once**, on your first PR, by posting a one-line comment (a bot walks you through it). The CLA is a **license grant, not an assignment**: you keep ownership of your contribution and your moral rights.

If NVEIL is useful to you, a ⭐ helps others discover it.

## Security

Found a vulnerability? Please report it **privately** — see **[SECURITY.md](.github/SECURITY.md)**. Don't open a public issue for security reports.

## License

NVEIL is **dual-licensed**:

- **Open source** — GNU **AGPL-3.0-or-later**: use, study, modify, and self-host freely. Note that AGPL §13 requires you to offer the corresponding source of any *modified* version you run as a network service. See [`LICENSE`](LICENSE).
- **Commercial** — to embed NVEIL in a closed-source product, or run a modified hosted version without publishing your changes, a commercial license removes the copyleft obligations. See [`COMMERCIAL-LICENSE.md`](licensing/COMMERCIAL-LICENSE.md) — contact `pierre.jacquet@nveil.com`.

## Contributors

Thanks to everyone who helps make NVEIL better 💜

<a href="https://github.com/nveil-ai/nveil/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=nveil-ai/nveil" alt="Contributors">
</a>

---

<p align="center">
  <a href="https://nveil.com">Website</a> &bull;
  <a href="https://app.nveil.com">Hosted platform</a> &bull;
  <a href="https://docs.nveil.com">Documentation</a> &bull;
  <a href="https://github.com/nveil-ai/nveil-toolkit">Toolkit (SDK · CLI · MCP)</a>
</p>
