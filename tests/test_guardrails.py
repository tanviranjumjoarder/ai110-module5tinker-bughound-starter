"""
Tests for the reliability changes I made to BugHound.
All of them run offline: StubClient stands in for Gemini, like MockClient does.
"""

import json

from bughound_agent import BugHoundAgent
from llm_client import MockClient
from reliability.risk_assessor import assess_risk


class StubClient:
    """Returns a fixed analyzer reply and a fixed fixer reply, so we can force model behavior."""

    def __init__(self, analyzer_reply, fixer_reply="", ):
        self.analyzer_reply = analyzer_reply
        self.fixer_reply = fixer_reply

    def complete(self, system_prompt, user_prompt):
        if "Return ONLY valid JSON" in system_prompt:
            return self.analyzer_reply
        return self.fixer_reply


def read_sample(name):
    with open(f"sample_code/{name}", encoding="utf-8") as f:
        return f.read()


def logs_text(result):
    return " | ".join(entry["message"] for entry in result["logs"])


# ---------- Part 2: validating the model's analysis ----------

def test_unknown_severity_from_model_falls_back_to_heuristics():
    # "Critical" is not a level the risk scorer understands; it used to count as zero risk.
    reply = json.dumps([{"type": "Reliability", "severity": "Critical", "msg": "bare except"}])
    agent = BugHoundAgent(client=StubClient(reply, fixer_reply=read_sample("mixed_issues.py")))
    result = agent.run(read_sample("mixed_issues.py"))

    assert "failed validation" in logs_text(result)
    assert all(i["severity"] in ("Low", "Medium", "High") for i in result["issues"])
    assert any(i["type"] == "Reliability" for i in result["issues"])  # heuristic finding


def test_severity_casing_is_normalized_not_rejected():
    reply = json.dumps([{"type": "Style", "severity": "low", "msg": "minor"}])
    agent = BugHoundAgent(client=StubClient(reply))
    issues = agent.analyze("def f():\n    return 1\n")
    assert issues == [{"type": "Style", "severity": "Low", "msg": "minor"}]


def test_empty_model_reply_is_logged_as_unavailable():
    agent = BugHoundAgent(client=StubClient(""))
    agent.analyze("def f():\n    print('x')\n")
    assert any("empty response" in e["message"] for e in agent.logs)


# ---------- Agent workflow: rejecting unusable AI fixes ----------

def test_fix_that_deletes_the_function_is_rejected():
    # MockClient's fixer returns a single comment; it used to replace the whole file.
    agent = BugHoundAgent(client=MockClient())
    result = agent.run(read_sample("flaky_try_except.py"))

    assert "def load_text_file" in result["fixed_code"]
    assert "LLM fix rejected (it deletes load_text_file)" in logs_text(result)


def test_fix_that_is_not_python_is_rejected():
    reply = json.dumps([{"type": "Reliability", "severity": "High", "msg": "bare except"}])
    agent = BugHoundAgent(client=StubClient(reply, fixer_reply="Here is your code: def ("))
    result = agent.run(read_sample("flaky_try_except.py"))
    assert "not valid Python" in logs_text(result)
    assert "def load_text_file" in result["fixed_code"]


# ---------- Part 3: invalid Python is never auto-applied ----------

def test_invalid_python_fix_is_high_risk():
    original = "def f(items):\n    for x in items:\n        try:\n            go(x)\n        except:\n            pass\n"
    # What the heuristic fixer actually produces for a nested bare except:
    broken = "def f(items):\n    for x in items:\n        try:\n            go(x)\n        except Exception as e:\n        # [BugHound] log or handle the error\n        pass\n"
    risk = assess_risk(original, broken, issues=[])
    assert risk["level"] == "high"
    assert risk["should_autofix"] is False
    assert "not valid Python" in risk["reasons"][0]


# ---------- Part 4: fixes that change printed output need a human ----------

def test_heuristic_print_fix_is_not_auto_applied():
    # Before the guardrail: risk LOW (95), auto-fix YES.
    result = BugHoundAgent(client=None).run(read_sample("print_spam.py"))
    assert result["risk"]["should_autofix"] is False
    assert any("changes what users see" in r for r in result["risk"]["reasons"])


def test_gemini_style_print_to_logger_fix_is_not_auto_applied():
    # The exact fix Gemini proposed for print_spam.py during testing.
    original = read_sample("print_spam.py")
    gemini_fix = (
        "import logging\n\nlogger = logging.getLogger(__name__)\n\n"
        "def greet(name, verbose=False):\n    if verbose:\n        logger.debug(\"Entering greet()\")\n\n"
        "    print(\"Hello\", name)\n    print(\"Welcome!\")\n\n    return True\n"
    )
    risk = assess_risk(original, gemini_fix, issues=[{"type": "Maintainability", "severity": "Low", "msg": "print"}])
    assert risk["should_autofix"] is False


def test_fix_that_keeps_output_can_still_auto_apply():
    # The guardrail should not make BugHound refuse everything.
    original = "def add(a, b):\n    print('adding')\n    return a + b\n"
    fixed = "def add(a, b):\n    print('adding')\n    return a + b\n"
    risk = assess_risk(original, fixed, issues=[{"type": "Style", "severity": "Low", "msg": "minor"}])
    assert risk["should_autofix"] is True


def test_print_inside_a_comment_is_not_flagged():
    code = "# just a comment\n# print( is mentioned here but not called\n"
    assert BugHoundAgent(client=None).run(code)["issues"] == []
