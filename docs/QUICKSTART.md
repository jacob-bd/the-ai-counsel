# Quick Start Guide

Get The AI Counsel running in under 5 minutes.

### 📺 Video Overview

Watch the video overview to see how to set up and run The AI Counsel:

<p align="center">
  <a href="https://youtu.be/OQV92Y_4Wo4" target="_blank">
    <img src="https://img.youtube.com/vi/OQV92Y_4Wo4/maxresdefault.jpg" alt="The AI Counsel Video Overview" width="75%">
  </a>
</p>

---

## 1. Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **[uv](https://docs.astral.sh/uv/)** - Install with: `curl -LsSf https://astral.sh/uv/install.sh | sh`

---

## 2. Install & Run

```bash
# Clone the repo
git clone https://github.com/jacob-bd/the-ai-counsel.git
cd the-ai-counsel

# Install dependencies
uv sync
npm install --prefix frontend

# Start the app
./start.sh
```

Open **http://localhost:5173** in your browser.

---

## 3. First-Time Setup

The Settings panel opens automatically on first launch.

### Option A: Use OpenRouter (Easiest)
1. Get a free API key at [openrouter.ai/keys](https://openrouter.ai/keys)
2. Paste it in **LLM API Keys** → **OpenRouter**
3. Click **Test** (auto-saves on success)
4. Go to **Council Config** → Select models for your council (saves automatically)

### Option B: Use Ollama (Free & Local)
1. Install [Ollama](https://ollama.com/)
2. Pull a model: `ollama pull llama3.1`
3. Start Ollama: `ollama serve`
4. In Settings → **LLM API Keys** → Click **Connect** for Ollama
5. Go to **Council Config** → Enable "Local (Ollama)" → Select models for your **council** (saves automatically)

> **Advisors:** Once Ollama is connected in LLM API Keys, Advisor Setup lists Ollama models automatically — you do **not** need to enable the council "Local (Ollama)" toggle for advisors.

### Option C: Use Direct APIs
1. Get API keys from your preferred providers (OpenAI, Anthropic, Google, OpenCode Zen/Go, etc.)
2. Enter keys in **LLM API Keys** → **Direct LLM Connections**
3. Click **Test** for each (auto-saves on success)
4. Go to **Council Config** → Enable "Direct Connections" → Select models (saves automatically)

### Option D: Use OpenCode Zen / Go
- OpenCode ships both a free **Zen** tier (zero-cost `*-free` models — `minimax-m3-free`, `deepseek-v4-flash-free`, etc.) and a paid **Go** subscription tier (per-1M token pricing shown as an estimate; flagged with a subscription note in the cost report).
- Use a single shared `opencode_api_key` (covers both Zen and Go). Add it in **LLM API Keys** → **OpenCode Zen & Go** → **Test**.
- Model IDs in Council/Advisor pickers: `opencode-zen:<model>` and `opencode-go:<model>`.
- Custom endpoints hosted at `https://opencode.ai/...` are also auto-detected as zero-cost.

---

## 4. Your First Council Query

1. Click **+ New Council** in the sidebar (or use the welcome screen)
2. **Configure your council** on the welcome screen — add members, pick a chairman (Full Deliberation only), or load a preset
3. Type your question
4. (Optional) Toggle **Web Search** for real-time grounding
5. Press **Enter**

Watch as:
- **Stage 1**: Each council member responds independently
- **Stage 2**: Models anonymously rank each other's responses
- **Stage 3**: Chairman synthesizes the final answer

---

## 4b. Your First Advisor Debate

1. Click **+ New Advisors** in the sidebar
2. Type a question or a decision to debate (e.g., "Should we rewrite our backend in Go?")
3. Configure the debate options:
   - Select 2 to 4 advisor personas (Skeptic, Strategist, Ethicist, etc.)
   - Set the number of back-and-forth rounds (3 to 10)
   - Choose a default model or assign specific models to individual personas — models from all **enabled** providers appear here
   - *(Optional)* Save your lineup as a **preset** from Model Assignment (personas, models, rounds, web search — not the debate question)
4. Click **Start Debate** and watch the advisors debate each other by name, culminating in a structured consensus verdict with a recommended action plan!

Use Advisors for questions with tradeoffs, risks, disagreement, prioritization, or a real decision to make. For simple answer generation ("give me one fact", "summarize this", "what is X?"), start with Council mode instead; Advisors are intentionally prompted to argue and may turn simple prompts into debates over criteria.

---

## 5. Deliberation Modes

Choose your deliberation type and depth:

| Mode / System | What Happens | Best For |
|------|--------------|----------|
| **Chat Only (Council)** | Just Stage 1 — quick individual responses | Quick model comparisons |
| **Chat + Ranking (Council)** | Stages 1 & 2 — see peer rankings and scores | Peer review without synthesis |
| **Full Deliberation (Council)** | All 3 stages — complete synthesis (default) | Broad, highly accurate synthesis |
| **LLM Advisors (Advisory)** | Persona-driven debate across configurable rounds | Complex strategic/moral decisions |

---

## 6. Quick Tips

- **Mix model families** in the council for diverse perspectives (e.g., GPT + Claude + Gemini)
- **Assign specific models to personas**: Give *The Skeptic* a highly detailed model (like Claude) and *The Pragmatist* a fast model (like Groq)
- **Advisor presets**: Save recurring panels (e.g., "Startup Review") from Advisor Setup → Model Assignment
- **Use Council for direct answers** and **Advisors for decisions/debates**. This keeps persona debate from overcomplicating simple prompts.
- **Use Groq** for ultra-fast council inference
- **Use Ollama** for unlimited, free local queries (great for local Chairman synthesis using a model like `granite4:1b`)
- **"I'm Feeling Lucky"** randomizes your council composition
- **Customize Personas**: Go to **Settings** → **Advisors** to edit name, description, emoji, and prompt for any advisor persona
- **Abort anytime** with the stop button in the sidebar

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Models not appearing | Enable the provider in **Settings → Council Config** toggles; verify API key / Ollama connection. Toggles are global — they apply to both Council and Advisor pickers |
| Rate limit errors | Use Groq (14k/day) or Ollama (unlimited) |
| Port conflict | Backend uses 8001, frontend uses 5173 |
| node_modules errors | `rm -rf frontend/node_modules && npm install --prefix frontend` |

---

## Next Steps

- Explore **System Prompts** to customize model behavior
- Configure **Web Search** providers (Tavily, Brave) for better results
- Adjust **Temperature** sliders for creativity control
- **Export** your council config to share or backup
- **Enable multi-round debate** — see [Council Debate Config Guide](COUNCIL-DEBATE-CONFIG.md) for a full walkthrough of critique modes, round settings, and real-world examples

For full documentation, see [README.md](README.md).

---

<p align="center">
  <em>Ask the council. Get better answers.</em>
</p>
