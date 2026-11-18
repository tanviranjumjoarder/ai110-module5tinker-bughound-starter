# BugHound Mini Model Card (Reflection)

I ran BugHound in both modes (Heuristic and Gemini) before and after my changes. Every run quoted here is saved in [`evidence/`](evidence/).

---

## 1) What is this system?

**Name:** BugHound
**Purpose:** Analyze a short Python snippet, propose a fix, check how risky that fix is, and decide whether it can be applied automatically or needs a human to review it.
**Intended users:** Students learning how agentic workflows and AI reliability work. It's a teaching tool, not something to point at a real codebase.

---

## 2) How does it work?

BugHound runs the same five steps every time, and logs each one to the "Agent trace":

1. **Plan:** it decides to do a quick scan and propose a fix. This step is fixed text; nothing is really planned yet.
2. **Analyze:** it finds issues. In heuristic mode it uses three simple rules: `print(` calls, a bare `except:`, and `TODO`. In Gemini mode it sends the code and a prompt asking for a JSON list of issues. If the reply is empty, isn't JSON, or (after my change) has a severity that isn't Low/Medium/High, it falls back to the heuristic rules.
3. **Act:** it proposes a fix. The heuristic fixer swaps `print(` for `logging.info(` and rewrites `except:` as `except Exception as e:`. In Gemini mode the model rewrites the whole snippet. After my change, the agent rejects a model "fix" that isn't valid Python or deletes a function, and uses the heuristic fixer instead.
4. **Test:** `reliability/risk_assessor.py` scores the fix from 0 to 100. Points come off for issue severity, a much shorter file, removed `return`s, and a changed bare except. My changes added "not valid Python" and "changes printed output" to that list.
5. **Reflect:** if the risk level is low (and, after my change, the fix doesn't change printed output), BugHound says the fix can be auto-applied. Otherwise it recommends human review.

The key idea: Gemini only ever *suggests* (issues and a fix). The decision to act is always made by the plain Python rules in the risk assessor, so it can be read and tested.

---

## 3) Inputs and outputs

**Inputs I tried:**

- All four samples: `cleanish.py` (should be left alone), `print_spam.py` (prints, one inside an `if`), `flaky_try_except.py` (bare except around file reading), `mixed_issues.py` (TODO + print + bare except).
- Three "weird" inputs: an empty file, a file with only comments (one mentions `print(`), and a bare `except:` nested inside a `for` loop.
- They're all short functions (5 to 9 lines), mostly built around try/except and print.

**Outputs:**

- **Issues found:** Code Quality / Readability (print), Reliability / Correctness (bare except), Maintainability (TODO). Gemini also found a Resource Management issue (the file isn't closed if `read()` fails).
- **Fixes proposed:** heuristic: print → `logging.info`, `except:` → `except Exception as e:` plus a comment. Gemini: everything from small edits to a whole new `validate_input()` function, and a clean `with open(...)` rewrite.
- **Risk reports:** `cleanish.py` was low/auto-fix every time. Anything with a bare except landed at medium or high (no auto-fix). The interesting cases were the print fixes and the "weird" inputs. See the before/after table in section 5.

---

## 4) Reliability and safety rules

**Rule A: issue severity deductions** (High −40, Medium −20, Low −5)

- *What it checks:* how serious the detected issues are.
- *Why it matters:* serious problems usually need bigger, riskier edits.
- *False positive:* it scores the **issues**, not the **fix**. A perfect one-line fix for a High issue still loses 40 points, so a good fix for a bare except can never be auto-applied.
- *False negative:* any severity it doesn't recognize counts as zero. Before my change, a model reply labeled `"Critical"` scored **100, LOW risk, auto-fix YES** (`tests_without_guardrails.txt`, first failure). Low-severity issues also barely count, so a "Low" print fix that changes behavior sailed through.

**Rule B: "Return statements may have been removed"** (−30 if `return` is in the original but not the fix)

- *What it checks:* whether the fix deleted the function's return value, a classic way to change behavior.
- *Why it matters:* a missing return silently turns results into `None`.
- *False positive:* it's a plain text search, so a fix that renames a variable called `returned_value` or removes a comment mentioning "return" also trips it.
- *False negative:* it only checks whether the word exists at all. A fix that removes one of three returns, or changes `return data` to `return None`, isn't caught.

**Rule C (mine): "Fixed code is not valid Python"** → score 0, high, never auto-fix

- *Why:* the heuristic fixer produces broken code for a nested `except:` (it assumes 8-space indentation). Before, that broken fix scored medium 55; it wasn't auto-applied only by luck.
- *False positive:* none for valid input. If the *original* snippet was already broken Python, the fix will be too, and it's flagged high; that's arguably right.
- *False negative:* valid Python can still be wrong. This rule only catches fixes that don't run at all.

**Rule D (mine, the Part 4 guardrail): "Fix removes or rewrites print() calls"** → −30 and never auto-fix

- *Why:* replacing `print` with logging changes what the user sees. At the default level, `logging.info` and `logging.debug` show nothing. Also, `print("Hello", name)` → `logging.info("Hello", name)` is a bug, because logging treats `name` as a format argument.
- *False positive:* a team that really does want all prints turned into logging will have to approve each one by hand.
- *False negative:* it only knows about `print`. A fix that changes a printed message's text, or removes `sys.stdout.write`, gets through.

---

## 5) Observed failure modes

**1. Unsafe confidence: a behavior-changing fix was marked safe to auto-apply (both modes).**
`print_spam.py` in heuristic mode: the fix rewrote three prints as `logging.info(...)`, including the broken `logging.info("Hello", name)`. Risk: **LOW 95, auto-fix YES**. In Gemini mode, the model quietly changed the `verbose` print to `logger.debug(...)`, so that message never appears. Risk: **LOW 95, auto-fix YES**. The only deduction was −5 for a "Low" issue. *Should have happened:* human review, because the fix changes output. Fixed by Rule D; now **MEDIUM 65, auto-fix NO** in both modes.

**2. The "fix" deleted the whole file (app's Heuristic mode).**
The app's "Heuristic only" mode doesn't run pure heuristics. It uses `MockClient`, whose fixer returns one comment line. For every sample with issues, the proposed fix was a one-line file. For the comments-only input, the risk check scored that 95 and said **auto-fix YES**, because the "much shorter" rule only fires when the fix is under half the original length, and 1 line out of 2 isn't under half. *Should have happened:* reject the fix. Fixed in the agent: a fix that deletes a function, or isn't valid Python, is rejected and the heuristic fixer is used instead.

**3. Over-editing by Gemini.**
On `mixed_issues.py`, Gemini's first fix added a new `validate_input()` function that raises `TypeError`. The original returned 0 for bad input (through the bare except), so this changed behavior. It also deleted the TODO comment and the print. Risk said medium (no auto-fix), which was right, but the reasons never mention "new function added" or "now raises." On a second run with the same prompt, Gemini made a much smaller edit, so how much it over-edits isn't predictable.

**4. Broken code from the heuristic fixer.**
For a bare `except:` nested in a loop, the heuristic fixer produced code with wrong indentation that won't run. It was scored medium 55 before my change (not auto-fixed, but only because of the High-severity deduction). Now Rule C flags it as **high risk, "not valid Python."**

**5. False positive on comments.**
A comments-only file that mentions `print(` was flagged as having print statements and "fixed" by rewriting the comment, with auto-fix YES. Fixed: the heuristic analyzer now ignores text after `#`.

| Input | Before (risk, auto-fix) | After (risk, auto-fix) |
|---|---|---|
| print_spam.py, heuristic | low 95, **YES** | medium 65, NO |
| print_spam.py, Gemini | low 95, **YES** | medium 65, NO |
| comments only, app Heuristic mode | low 95, **YES** (file replaced by a comment) | low 100, YES (no change made) |
| nested bare except, heuristic | medium 55, NO (broken code) | high 0, NO ("not valid Python") |
| model says severity "Critical" (stub) | low 100, **YES** | falls back to heuristics |
| cleanish.py | low 100, YES | low 100, YES (still allowed) |

---

## 6) Heuristic vs Gemini comparison

- **What Gemini found that heuristics didn't:** the resource leak in `flaky_try_except.py` (the file isn't closed if `read()` fails), and the point that a bare except also swallows `KeyboardInterrupt` / `SystemExit`. The heuristics only know three patterns.
- **What heuristics caught consistently:** exactly their three patterns, every time, with the same severities (print = Low, TODO = Medium, bare except = High). Gemini's labels varied: it called the TODO "Low" while the heuristics say Medium, and once rated the bare except Medium instead of High.
- **How the fixes differed:** the heuristic fixer is mechanical and sometimes wrong (the `logging.info("Hello", name)` bug, the broken indentation). Gemini's fixes read more naturally (`with open(...)`, `except Exception:`), but they decide for themselves how much to change. Sometimes that's one line, sometimes a whole new function. They also changed between runs on the same input.
- **Did the risk scorer match my intuition?** Not at first. It worried about the wrong thing (issue severity) and missed the thing I cared about (the fix changing behavior). It was most wrong on print fixes, which it treated as the safest kind of change. After my changes it agreed with me on every input I tried, but only for the kinds of risk I wrote rules for.

---

## 7) Human-in-the-loop decision

**Scenario:** a fix that changes what the program outputs or how it fails. Examples: removing or rewriting a `print`, changing what an `except` block returns, or adding a new `raise`. Even if the code is "better," someone has to decide whether callers and users depend on the old behavior.

- **Trigger:** I implemented the print part. The fix has fewer `print(` calls than the original (comments ignored). The next triggers I'd add are "the fix adds a `raise`" and "the fix changes what an `except` block returns."
- **Where:** in `risk_assessor.py`, as a hard veto on `should_autofix`, not just a score deduction. A point penalty can be outweighed; a rule like "output changed → human decides" shouldn't be. It's tested in `tests/test_guardrails.py` (fails on the original code, passes now).
- **Message to the user:** "Fix removes or rewrites 2 print() call(s), which changes what users see." It appears in the Reasons list, and the trace says "Human review recommended."

---

## 8) Improvement idea

**Score the fix, not the issues, with a "behavior diff" check.** Compare the original and fixed code with Python's `ast` module, not text search. Count `return`, `raise`, `except` handlers, and calls like `print`. If any of those counts change, require human review. This replaces three fragile string checks with one solid one, and it would have caught every behavior change I saw, including Gemini's new `raise TypeError`. It's about 30 lines and easy to test with the MockClient pattern. It's the same idea as Rule D, applied to the other ways a fix can change behavior.

---

## What I changed (summary)

| Part | Change | File | Test |
|---|---|---|---|
| 2: analysis | Reject model issues whose severity isn't Low/Medium/High (fall back to heuristics); normalize "high" → "High"; log empty replies as "model unavailable" | `bughound_agent.py` | `test_unknown_severity_...`, `test_severity_casing_...`, `test_empty_model_reply_...` |
| Workflow | Reject a model fix that isn't valid Python or deletes a function; use the heuristic fixer | `bughound_agent.py` | `test_fix_that_deletes_...`, `test_fix_that_is_not_python_...` |
| 3: risk | New signal: fix isn't valid Python → high, never auto-fix | `reliability/risk_assessor.py` | `test_invalid_python_fix_is_high_risk` |
| 4: guardrail | Fix removes or rewrites print() → −30 and never auto-fix | `reliability/risk_assessor.py` | `test_heuristic_print_fix_...`, `test_gemini_style_print_...`, `test_fix_that_keeps_output_...` |
| Bug fixes | Heuristic analyzer ignores `print(` in comments; the Gemini client now actually uses the temperature slider | `bughound_agent.py`, `llm_client.py` | `test_print_inside_a_comment_...` |

All 18 tests pass. On the original starter code, 9 of my 10 new tests fail. The 10th checks that safe fixes can still be auto-applied, so it passes both ways. Output is in `evidence/tests_with_guardrails.txt` and `evidence/tests_without_guardrails.txt`.

**How I used AI:** I worked with an AI coding assistant. It read the codebase with me, ran every sample in both modes, and drafted the guardrails and tests. I decided which failures mattered and where each rule should live. **Accepted:** its suggestion to put the print rule in the risk assessor as a veto on auto-fix, not only a point deduction. **Rejected:** fixing the heuristic fixer's indentation bug directly. I kept the bug and added the "not valid Python" rule instead, because the lab is about the agent catching its own bad output, and a general syntax check also protects against broken Gemini fixes.
