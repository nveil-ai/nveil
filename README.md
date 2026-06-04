<p align="center">
  <img src="https://raw.githubusercontent.com/nveil-ai/nveil-toolkit/main/assets/logo.png" alt="NVEIL" width="180">
</p>

<h1 align="center">NVEIL — Community Edition</h1>

<p align="center">
  <strong>Chat with your data. Get production-ready visualizations.<br>Self-hosted, private, and open source.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0--or--later-blue" alt="License"></a>
  <a href="https://docs.nveil.com"><img src="https://img.shields.io/badge/docs-docs.nveil.com-blue" alt="Docs"></a>
  <a href="https://nveil.com"><img src="https://img.shields.io/badge/website-nveil.com-black" alt="Website"></a>
</p>

<p align="center">
  <a href="#why-nveil">Why NVEIL</a> &bull;
  <a href="#run-nveil">Run it</a> &bull;
  <a href="#use-it-from-your-code-optional">From code</a> &bull;
  <a href="#contributing">Contributing</a> &bull;
  <a href="#license">License</a>
</p>

---

**NVEIL is a self-hosted AI platform for data visualization.** Open it in your browser, point it at your data, and describe what you want in plain language — through a chat interface. NVEIL turns that into interactive, production-ready visualizations: 2D and 3D charts, geospatial maps, scientific and medical imaging, and more.

**Your raw data never leaves your infrastructure.** Only the *shape* of it — column names, types, and aggregate statistics — is sent to the model. The data itself is processed and rendered where you run NVEIL.

This repository is the **Community Edition**: the complete platform, free and open under the AGPL, that you run yourself.

<p align="center">
  <img src="https://raw.githubusercontent.com/nveil-ai/nveil-toolkit/main/assets/ai-chat.png" alt="NVEIL chat — conversational data exploration with a geospatial heatmap" width="800">
</p>

## Why NVEIL?

- 💬 **Conversational** — describe what you want; no plotting code, no dashboards to wire by hand.
- 🔒 **Private by design** — raw data stays on your infrastructure; only metadata reaches the AI.
- 🎯 **Deterministic** — visualizations come from constraint solving, not guesswork: same request → same result, every time.
- 📊 **Any kind of chart** — 2D, 3D, geospatial, scientific, medical imaging, biosignals, network graphs, and 50+ more.
- 🤖 **Bring your own model** — Gemini, OpenAI, Anthropic, Mistral, or a local model (Ollama, llama.cpp, any OpenAI-compatible endpoint).
- 🗂️ **A real app** — chat, dashboards, file management, multi-user rooms, internationalization.

## Run NVEIL

NVEIL runs on **Docker**. There are two ways to get it going.

### 🟢 Community setup — prebuilt images *(lightweight, recommended)*

The fast path: download one Compose file, configure once, pull the images, run. No build, no source checkout, no dev tooling.

```bash
# 1. Download the Compose file — the only file you need.
curl -O https://raw.githubusercontent.com/nveil-ai/nveil/main/docker-compose.yaml

# 2. Configure — a guided wizard writes your .env (DB passwords, secrets, LLM provider).
docker compose up setup                 # then open http://localhost:3000

# 3. Pull the prebuilt images and start.
docker compose up -d

# 4. Open the app.
#    https://localhost:8000
```

### 🛠️ Developer setup — build from source

For contributing or running the full stack (builds from source, live reload, TEST mode, optional Langfuse tracing) — everything lives in `docker-compose.dev.yml`:

```bash
git clone https://github.com/nveil-ai/nveil.git
cd nveil

# 1. Configure — a guided wizard writes your .env (DB passwords, secrets, LLM provider).
docker compose -f docker-compose.dev.yml up setup      # then open http://localhost:3000

# 2. Build & start from source.
docker compose -f docker-compose.dev.yml --profile core up --build -d

# 3. Open the app.
#    https://localhost:8000
```

> **Optional — LLM tracing** with the bundled Langfuse (opt-in):
> `docker compose -f docker-compose.dev.yml --profile core --profile tracing up -d` → http://localhost:3030

Full guide: **[docs.nveil.com](https://docs.nveil.com)**.

## Use it from your code *(optional)*

The web app is the main way to use NVEIL. If you'd rather drive it **programmatically** — from a Python script, your terminal, or an AI agent — there's an optional client, the **NVEIL Toolkit**:

```bash
pip install nveil
```

It gives you a Python SDK, a `nveil` CLI, and an MCP server for agents (Claude Code, Cursor, …), all pointed at your NVEIL instance. See **[nveil-toolkit](https://github.com/nveil-ai/nveil-toolkit)**.

## Contributing

Contributions are welcome! The developer setup above is all you need to get started.

Pull requests are accepted under the project's **[Contributor License Agreement](CLA.md)** — you sign it **once**, on your first PR, by posting a one-line comment (a bot walks you through it). The CLA is a **license grant, not an assignment**: you keep ownership of your contribution and your moral rights.

Bug reports and feature ideas are welcome via [GitHub Issues](https://github.com/nveil-ai/nveil/issues).

## License

NVEIL is **dual-licensed**:

- **Open source** — GNU **AGPL-3.0-or-later**: use, study, modify, and self-host freely. Note that AGPL §13 requires you to offer the corresponding source of any *modified* version you run as a network service. See [`LICENSE`](LICENSE).
- **Commercial** — to embed NVEIL in a closed-source product, or run a modified hosted version without publishing your changes, a commercial license removes the copyleft obligations. See [`COMMERCIAL-LICENSE.md`](COMMERCIAL-LICENSE.md) — contact `pierre.jacquet@nveil.com`.

---

<p align="center">
  <a href="https://nveil.com">Website</a> &bull;
  <a href="https://docs.nveil.com">Documentation</a> &bull;
  <a href="https://app.nveil.com">Hosted platform</a>
</p>
