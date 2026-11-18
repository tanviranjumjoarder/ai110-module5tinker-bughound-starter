# 🐶 BugHound

BugHound is a small, agent-style debugging tool. It analyzes a Python code snippet, proposes a fix, and runs basic reliability checks before deciding whether the fix is safe to apply automatically.

---

## What BugHound Does

Given a short Python snippet, BugHound:

1. **Analyzes** the code for potential issues  
   - Uses heuristics in offline mode  
   - Uses Gemini when API access is enabled  

2. **Proposes a fix**  
   - Either heuristic-based or LLM-generated  
   - Attempts minimal, behavior-preserving changes  

3. **Assesses risk**  
   - Scores the fix  
   - Flags high-risk changes  
   - Decides whether the fix should be auto-applied or reviewed by a human  

4. **Shows its work**  
   - Displays detected issues  
   - Shows a diff between original and fixed code  
   - Logs each agent step

---

## Setup

### 1. Create a virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# or
.venv\Scripts\activate      # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Running in Offline (Heuristic) Mode

No API key required.

```bash
streamlit run bughound_app.py
```

In the sidebar, select:

* **Model mode:** Heuristic only (no API)

This mode uses simple pattern-based rules and is useful for testing the workflow without network access.

---

## Running with Gemini

### 1. Set up your API key

Copy the example file:

```bash
cp .env.example .env
```

Edit `.env` and add your Gemini API key:

```text
GEMINI_API_KEY=your_real_key_here
```

### 2. Run the app

```bash
streamlit run bughound_app.py
```

In the sidebar, select:

* **Model mode:** Gemini (requires API key)
* Choose a Gemini model and temperature

BugHound will now use Gemini for analysis and fix generation, while still applying local reliability checks.

---

## Running Tests

Tests focus on **reliability logic** and **agent behavior**, not the UI.

```bash
pytest
```

You should see tests covering:

* Risk scoring and guardrails
* Heuristic fallbacks when LLM output is invalid
* End-to-end agent workflow shape

---

## My changes (Week 9 Tinker)

BugHound used to auto-approve fixes that changed program behavior, accept model output with severities it didn't understand, and, in the app's Heuristic mode, "fix" files by replacing them with a single comment. I added guardrails so the agent catches these cases and hands them to a human:

| Change | Where | Why |
|---|---|---|
| Model issues must have severity Low/Medium/High, or BugHound falls back to heuristics | `bughound_agent.py` (`_validate_issues`) | A "Critical" issue used to count as zero risk: score 100, auto-fix YES |
| A model fix that isn't valid Python or deletes a function is rejected | `bughound_agent.py` (`_check_fix_shape`) | MockClient's placeholder used to replace the whole file |
| A fix that isn't valid Python is high risk and never auto-applied | `reliability/risk_assessor.py` | The heuristic fixer breaks indentation for a nested `except:` |
| A fix that removes or rewrites `print()` calls is never auto-applied | `reliability/risk_assessor.py` | print → logging hides output (and `logging.info("Hello", name)` is a bug), yet it was rated LOW / auto-fix YES |
| `print(` inside comments is ignored; the temperature slider now reaches Gemini | `bughound_agent.py`, `llm_client.py` | False positive; the setting was silently ignored |

Results on the same inputs:

```text
print_spam.py (heuristic)    before: low 95, auto-fix YES   after: medium 65, auto-fix NO
print_spam.py (Gemini)       before: low 95, auto-fix YES   after: medium 65, auto-fix NO
nested bare except           before: medium 55 (broken code) after: high 0, "not valid Python"
comments-only file           before: low 95, auto-fix YES   after: no issues, code unchanged
cleanish.py                  before: low 100, auto-fix YES  after: low 100, auto-fix YES (still allowed)
```

Tests: `pytest` runs 18 tests, all passing. On the original starter code, 9 of the 10 new tests in `tests/test_guardrails.py` fail. Full runs (offline, app Heuristic mode, Gemini, tests with and without the guardrails) are in [`evidence/`](evidence/). To rerun all inputs offline:

```bash
python evidence/run_all_inputs.py          # pure heuristics
python evidence/run_all_inputs.py --mock   # what the app's "Heuristic only" mode does
```

The reflection (workflow, rules, failure modes, heuristic vs Gemini, human-review triggers, improvement idea) is in [`model_card.md`](model_card.md).
