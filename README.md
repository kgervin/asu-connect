# ASU Connect

An MCP server that lets any AI agent answer trusted questions about Arizona State University
programs, transfer credit, and non-degree classes — using governed, source-cited, mock data.

> **Bobathon entry** · IBM Bobathon North America · WOW track · Dec 2, 2026  
> **Primary dev tool:** IBM Bob  
> **Data:** Public/mock only — no internal EdPlus data or real student records.

---

## What it does

Instead of every university building its own chatbot, ASU Connect exposes three governed tools
that a student's existing AI agent can call:

| Tool | What it answers |
|------|----------------|
| `estimate_transfer_credits` | "How many of my community-college credits transfer to ASU?" |
| `find_programs` | "Which online ASU degree programs match my goals?" |
| `check_nondegree_options` | "What class can I take next term without applying, and what will it cost?" |

Every response includes a plain-English summary, itemized data, a source URL, a disclaimer, and
action-first next steps — so the agent can relay accurate, cited answers directly to the student.

---

## Quick start

### Requirements

- Python 3.11+
- [fastmcp](https://github.com/jlowin/fastmcp) (installed automatically)

### Install

```bash
git clone https://github.com/<your-username>/asu-connect.git
cd asu-connect
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run the server

```bash
python -m asu_connect.server
```

The server starts on stdio and prints a ready message to stderr. It is now available for any
MCP-capable agent to connect to.

### Run the tests

```bash
pytest tests/ -v
```

All 30 tests should pass in under 1 second each.

---

## Agent compatibility

ASU Connect uses the **standard MCP protocol over stdio**. Any agent with an MCP client connects
without changes to the server. The constraint is always on the agent side, not the server.

| Agent | MCP support | How to connect |
|---|---|---|
| **IBM Bob** | ✅ Yes | `.bob/mcp.json` — see below |
| **Claude Desktop** | ✅ Yes | `claude_desktop_config.json` — see below |
| **Cursor** | ✅ Yes | `.cursor/mcp.json` — same config format as Bob |
| **Zed** | ✅ Yes | Zed settings → Context Servers |
| **ChatGPT** | ❌ No | ChatGPT uses OpenAI Actions, not MCP — incompatible |
| **Gemini** | ❌ No | Gemini does not support MCP — incompatible |

---

## Connect to IBM Bob

Add the following to your Bob workspace `mcp.json` (`.bob/mcp.json` in the project root):

```json
{
  "mcpServers": {
    "asu-connect": {
      "command": "/absolute/path/to/asu-connect/.venv/bin/python3",
      "args": ["-m", "asu_connect.server"],
      "cwd": "/absolute/path/to/asu-connect",
      "env": {
        "PYTHONPATH": "/absolute/path/to/asu-connect/src"
      }
    }
  }
}
```

Replace `/absolute/path/to/asu-connect` with the actual path on your machine.

Once connected, try the Maya demo question:

> "I have 45 credits from a community college and work full time.
> I want an online construction management degree. What's my fastest, cheapest path?"

Bob will call all three tools and return a combined plan with sources cited.

---

## Connect to Claude Desktop

Add the `asu-connect` entry to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "asu-connect": {
      "command": "/absolute/path/to/asu-connect/.venv/bin/python3",
      "args": ["-m", "asu_connect.server"],
      "cwd": "/absolute/path/to/asu-connect",
      "env": {
        "PYTHONPATH": "/absolute/path/to/asu-connect/src"
      }
    }
  }
}
```

Restart Claude Desktop after saving. The three ASU Connect tools will appear in the tools panel.

---

## Why ChatGPT and Gemini can't connect

ChatGPT uses **OpenAI Actions** (a REST/OpenAPI schema) and Gemini uses **Google Extensions** —
both are proprietary tool protocols incompatible with MCP. To connect ASU Connect to those agents
you would need to wrap the tools as an OpenAPI-spec HTTP server (for ChatGPT) or a Google
Extension (for Gemini). That is a post-MVP consideration; the MCP connector model is the
priority for this submission.

---

## Project structure

```
asu-connect/
├── src/asu_connect/
│   ├── server.py          # FastMCP server entry point
│   ├── middleware.py       # Input validation, logging, rate limiting
│   ├── response.py         # Standard response envelope (Apple/Nielsen/Netflix)
│   └── tools/
│       ├── estimate_transfer_credits.py
│       ├── find_programs.py
│       └── check_nondegree_options.py
├── data/
│   ├── programs.json          # Mock ASU degree programs (versioned)
│   ├── transfer_rules.json    # Mock transfer credit rules (versioned)
│   └── nondegree_options.json # Mock non-degree courses (versioned)
├── tests/
│   ├── test_middleware.py
│   └── test_tools.py
└── pyproject.toml
```

Data lives in versioned JSON files. Adding a new program or transfer rule requires no code change.

---

## Design principles

- **Nielsen heuristics** — responses always show status, errors always give a next step, no dead ends.
- **Apple HIG tone** — plain English, active voice, ≤ 20-word disclaimers, address the student as "you".
- **Netflix content design** — most important fact first, action-first `next_steps`, short field labels.

---

## Security & governance

- All inputs are validated (type check, 500-char limit, injection pattern rejection) before processing.
- Tool inputs are never logged — only tool name, timestamp, and result status are recorded.
- Rate limited to 20 calls per client per minute (in-memory).
- Read-only mock data — no writes, no personal data stored.
- All figures carry a disclaimer: *"This is an estimate. Verify the details with an ASU advisor."*

---

## Disclaimer

All data in this project is **mock data for demonstration purposes only**. It does not represent
official ASU programs, tuition, transfer credit policies, or enrollment figures. Always verify
with an official ASU advisor before making any academic or financial decisions.
