# Day 0 — Setup checklist

Goal: finish this page and you start Day 1 with a green environment — accounts made,
dependencies installed, both API keys verified with a real call, and the database
confirmed writable. Budget ~45–60 minutes.

Do the steps in order. Don't skip the verification step at the end — it's the whole point.

---

## 1. Accounts & keys (2 total)

### Anthropic (the agent's brain — the one paid dependency)
- [ ] Sign up / log in at https://console.anthropic.com
- [ ] Create an API key (API keys → Create key). Copy it somewhere safe.
- [ ] **Set a spend limit** (Billing → set a monthly cap, e.g. $5). This makes a
      runaway loop financially impossible. Do this now, not later.
- [ ] Check whether your account has trial credits — likely covers this whole project.

### Tavily (web search — free, no card)
- [ ] Sign up at https://tavily.com
- [ ] Copy your API key from the dashboard.
- [ ] Free tier = 1,000 credits/month (~100–200 agent runs). No credit card needed.
- [ ] (Student? Email support@tavily.com from your student address for 4 months of
      4,000 credits/month — optional.)

---

## 2. Local installs

- [ ] **Python 3.11 or newer** — check with `python3 --version`
      (get it from https://python.org if you're below 3.11)
- [ ] **Git** — check with `git --version`
- [ ] **VS Code** — https://code.visualstudio.com
- [ ] Skip for now: Node.js (only needed for the phase-2 React frontend),
      Docker (only if you later self-host Langfuse — we're using its hosted free tier).

---

## 3. Run the setup script

From this folder, in a terminal:

```bash
bash setup.sh
```

This creates a virtual environment, installs the Python dependencies, and makes
your `.env` file from the template.

Then open `.env` and paste in your two real keys:

```
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
```

`.env` is gitignored — your keys will never be committed. (`.env.example` stays in
the repo so reviewers see the shape without seeing secrets.)

---

## 4. Verify everything works (do not skip)

With the venv active:

```bash
source .venv/bin/activate
python verify_setup.py
```

You want to see all green:
- ✅ Python version OK
- ✅ ANTHROPIC_API_KEY found + a 1-token test call succeeded
- ✅ TAVILY_API_KEY found + a 1-credit test search succeeded
- ✅ SQLite database is writable

If any line is red, the script tells you what to fix. Don't move to Day 1 until
all four are green.

---

## 5. Wire up Claude in VS Code

- [ ] Open this project folder in VS Code (File → Open Folder). Open a file so the
      Claude icon appears — the ✱ / Spark icon only shows with a file open.
- [ ] Install the **Claude Code** extension: Extensions view (Ctrl/Cmd+Shift+X),
      search "Claude Code", install the one published by **Anthropic** (verified
      checkmark — avoid look-alikes). The extension bundles its own CLI, so there's
      nothing else to install.
- [ ] Sign in when prompted. Note: Claude Code needs a **Pro plan ($20/mo) or
      Console/API credits** — the Free web plan doesn't include it. Your Anthropic
      API key covers this.
- [ ] Open the panel: Command Palette (Ctrl/Cmd+Shift+P) → "Claude Code: Open Chat".
- [ ] The `CLAUDE.md` file in this repo is read automatically by Claude Code as
      project context — it's already written for you (see below). You don't need to
      do anything; just know that's why Claude "knows" your project.

You're ready for Day 1.
