import ast
import re
from typing import Dict, List


def _count_print_calls(code: str) -> int:
    """Number of print( calls in real code (comments ignored)."""
    code_only = "\n".join(line.split("#", 1)[0] for line in code.splitlines())
    return len(re.findall(r"\bprint\s*\(", code_only))


def assess_risk(
    original_code: str,
    fixed_code: str,
    issues: List[Dict[str, str]],
) -> Dict[str, object]:
    """
    Simple, explicit risk assessment used as a guardrail layer.

    Returns a dict with:
    - score: int from 0 to 100
    - level: "low" | "medium" | "high"
    - reasons: list of strings explaining deductions
    - should_autofix: bool
    """

    reasons: List[str] = []
    score = 100

    if not fixed_code.strip():
        return {
            "score": 0,
            "level": "high",
            "reasons": ["No fix was produced."],
            "should_autofix": False,
        }

    # ----------------------------
    # Part 3 risk signal: the fix must be valid Python
    # ----------------------------
    # A fix that does not even parse can never be auto-applied, no matter how
    # small the issues were. (The heuristic fixer produces this for a nested bare except.)
    try:
        ast.parse(fixed_code)
    except SyntaxError as e:
        return {
            "score": 0,
            "level": "high",
            "reasons": [f"Fixed code is not valid Python ({e.msg}, line {e.lineno})."],
            "should_autofix": False,
        }

    original_lines = original_code.strip().splitlines()
    fixed_lines = fixed_code.strip().splitlines()

    # ----------------------------
    # Issue severity based risk
    # ----------------------------
    for issue in issues:
        severity = str(issue.get("severity", "")).lower()

        if severity == "high":
            score -= 40
            reasons.append("High severity issue detected.")
        elif severity == "medium":
            score -= 20
            reasons.append("Medium severity issue detected.")
        elif severity == "low":
            score -= 5
            reasons.append("Low severity issue detected.")

    # ----------------------------
    # Structural change checks
    # ----------------------------
    if len(fixed_lines) < len(original_lines) * 0.5:
        score -= 20
        reasons.append("Fixed code is much shorter than original.")

    if "return" in original_code and "return" not in fixed_code:
        score -= 30
        reasons.append("Return statements may have been removed.")

    if "except:" in original_code and "except:" not in fixed_code:
        # This is usually good, but still risky.
        score -= 5
        reasons.append("Bare except was modified, verify correctness.")

    # ----------------------------
    # Part 4 guardrail: user-visible output changed
    # ----------------------------
    # Replacing print() with logging looks like a harmless style fix, but it changes
    # what the program shows: logging.info/debug output is hidden at the default
    # level, and print("Hello", name) -> logging.info("Hello", name) is a formatting
    # bug. A human has to decide whether that output is still needed.
    removed_prints = _count_print_calls(original_code) - _count_print_calls(fixed_code)
    output_changed = removed_prints > 0
    if output_changed:
        score -= 30
        reasons.append(
            f"Fix removes or rewrites {removed_prints} print() call(s), which changes what users see."
        )

    # ----------------------------
    # Clamp score
    # ----------------------------
    score = max(0, min(100, score))

    # ----------------------------
    # Risk level
    # ----------------------------
    if score >= 75:
        level = "low"
    elif score >= 40:
        level = "medium"
    else:
        level = "high"

    # ----------------------------
    # Auto-fix policy
    # ----------------------------
    should_autofix = level == "low" and not output_changed

    if not reasons:
        reasons.append("No significant risks detected.")

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "should_autofix": should_autofix,
    }
