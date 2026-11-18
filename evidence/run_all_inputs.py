# Runs BugHound on every sample plus three edge cases and prints issues, risk, diff and trace.
# Usage (from the repo root):  python evidence/run_all_inputs.py          # pure heuristics
#                              python evidence/run_all_inputs.py --mock   # what the app's Heuristic mode uses

import sys, os, difflib
sys.path.insert(0, os.getcwd())
from bughound_agent import BugHoundAgent
from llm_client import MockClient
CLIENT = MockClient() if "--mock" in sys.argv else None
cases = {f: open(os.path.join("sample_code", f)).read() for f in sorted(os.listdir("sample_code"))}
cases["(empty file)"] = ""
cases["(comments only)"] = "# just a comment\n# print( is mentioned here but not called\n"
cases["(nested bare except)"] = "def f(items):\n    for x in items:\n        try:\n            go(x)\n        except:\n            pass\n    return True\n"
for name, code in cases.items():
    r = BugHoundAgent(client=CLIENT).run(code)
    print("=" * 70); print(name)
    print("issues:", [(i["type"], i["severity"]) for i in r["issues"]])
    print("risk:", r["risk"]["level"], r["risk"]["score"], "autofix:", r["risk"]["should_autofix"], r["risk"]["reasons"])
    d = "\n".join(difflib.unified_diff(code.splitlines(), r["fixed_code"].splitlines(), lineterm="", n=0))
    print("diff:\n" + (d or "(none)"))
    print("trace:", " | ".join(f"{l['step']}: {l['message']}" for l in r["logs"]))
