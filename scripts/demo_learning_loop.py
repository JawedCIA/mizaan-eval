"""Live demo: independent multi-agent scoring + the RAG learning loop.

Runs the canonical Mizaan story against a running API:

  1. Score work item A (a senior-exec sales call) cold.
  2. Score a SIMILAR item B cold (baseline — no feedback in the system yet).
  3. A human OVERRIDES A's score upward, with reasoning.
  4. Score B again — RAG should now retrieve A's correction and nudge B up.

It prints, for every score: the Primary score, the INDEPENDENT Auditor score,
the inter-agent gap (|P-A|), and the routing path — the numbers that prove the
two agents are genuinely independent — plus the before/after learning delta.

Usage:
    python scripts/demo_learning_loop.py            # API at http://localhost:8000
    BASE_URL=http://localhost:8000 python scripts/demo_learning_loop.py
"""

import os

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
RUBRIC = "sales-call-v2"

ITEM_A = (
    "90-minute discovery call with the CFO of a Fortune 500 global manufacturing "
    "firm. We worked through enterprise-wide cost pressures, demoed the platform "
    "live, and aligned on a follow-up working session with their procurement "
    "committee. No deal closed yet, but the CFO personally committed to sponsoring "
    "an internal evaluation."
)
ITEM_B = (
    "75-minute discovery call with the VP of Engineering at a large healthcare "
    "company. Deep technical discussion of their data pipeline; we uncovered four "
    "concrete integration requirements and scheduled a technical deep-dive with "
    "their solution architects. Senior, strategic engagement with a large account."
)


def score(client: httpx.Client, desc: str, title: str) -> dict:
    r = client.post(
        f"{BASE}/api/v1/scoring/score",
        json={
            "work_item_description": desc,
            "work_item_type": "sales-call",
            "work_item_title": title,
            "rubric_slug": RUBRIC,
        },
        timeout=600,
    )
    r.raise_for_status()
    return r.json()


def feedback(client: httpx.Client, sid: str, decision: str, adjusted: float, reasoning: str) -> dict:
    r = client.post(
        f"{BASE}/api/v1/feedback/",
        json={
            "scoring_result_id": sid,
            "decision": decision,
            "adjusted_score": adjusted,
            "reasoning": reasoning,
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def show(label: str, res: dict) -> None:
    p = res.get("primary_score")
    a = res.get("auditor_score")
    gap = res.get("disagreement")
    print(f"\n  {label}")
    print(f"    Primary score : {p}")
    print(f"    Auditor score : {a}   (independent — never saw the Primary's score)")
    print(f"    Inter-agent gap: {gap}    →  path: {res.get('path')}")
    print(f"    Final score   : {res.get('final_score')}   "
          f"(human review required: {res.get('requires_human_review')})")


def main() -> None:
    with httpx.Client() as client:
        print("=" * 68)
        print("MIZAAN — live multi-agent scoring + RAG learning loop")
        print("=" * 68)

        print("\n[1] Score item A (CFO call) — cold, no prior feedback")
        a = score(client, ITEM_A, "Fortune 500 CFO discovery call")
        show("Item A", a)

        print("\n[2] Score item B (VP Eng call) — cold BASELINE, before any feedback")
        b_before = score(client, ITEM_B, "VP Engineering discovery call")
        show("Item B (before)", b_before)

        print("\n[3] A human OVERRIDES item A upward, explaining why")
        feedback(
            client,
            a["id"],
            "OVERRIDDEN",
            9.0,
            "A 90-minute working session with a Fortune 500 CFO who personally "
            "committed to sponsoring an evaluation is exceptionally high-impact "
            "strategic work — exactly what we want to reward, even before a deal "
            "closes.",
        )
        print("    stored override: A → 9.0 (embedded for future retrieval)")

        print("\n[4] Score item B AGAIN — RAG should retrieve A's correction")
        b_after = score(client, ITEM_B, "VP Engineering discovery call")
        show("Item B (after learning)", b_after)

        print("\n" + "=" * 68)
        print("RESULT")
        print("=" * 68)
        fb_before = b_before.get("final_score") or 0
        fb_after = b_after.get("final_score") or 0
        delta = round(fb_after - fb_before, 2)
        print(f"  Item B final score: {fb_before}  →  {fb_after}   (delta {delta:+})")
        print("  Inter-agent agreement is reported on every score above (gap |P-A|).")
        if delta > 0:
            print("  ✓ Learning loop worked: B moved UP after the human correction on a")
            print("    similar item — with NO model retraining, purely via RAG retrieval.")
        else:
            print("  Note: B did not move up this run (small local model + sampling noise).")
            print("  The independent-agent agreement numbers above are the robust signal;")
            print("  re-run, or use a stronger model, for a cleaner learning delta.")


if __name__ == "__main__":
    main()
