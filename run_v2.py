"""
Run v2 over every test case and save the answers to results/v2.json.

    python run_v2.py

Takes about 7 minutes — there is a pause between cases so Groq's
rate limit is not hit.
"""

import json
import os
import time

from bot import run_v2

SLEEP_SECONDS = 20
TEST_CASES = os.path.join("tests", "test_cases.json")
OUT_FILE = os.path.join("results", "v2.json")


def main():
    os.makedirs("results", exist_ok=True)

    with open(TEST_CASES, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    print(f"{len(cases)} cases loaded\n")

    out = []
    for c in cases:
        print(f"case {c['id']:>2} ...", end=" ", flush=True)
        try:
            category, query, answer = run_v2(c["user_message"], c["followup_answers"])
            out.append({
                "id": c["id"],
                "type": c["type"],
                "expected_category": c["category"],
                "detected_category": category,
                "query": query,
                "answer": answer,
            })
            print("ok")
        except Exception as e:
            out.append({"id": c["id"], "error": str(e)})
            print("FAILED:", e)
        time.sleep(SLEEP_SECONDS)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    failed = sum(1 for r in out if "error" in r)
    print(f"\ndone — {len(out)} cases, {failed} failed")
    print(f"saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
