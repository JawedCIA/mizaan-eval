"""Injection test: prove the RAG learning loop's untested link.

The pipeline + independent dual-agent scoring are already proven live. The one
segment never exercised is the *injection* path that IS the product:

    retrieved human correction  ->  formatted into the scorer prompt  ->  LLM shifts its score

This script isolates that link, with NO code change, using the advisor's recipe:

  X   a modest-sounding item that should score LOW cold (headroom to rise)
  Xp  a close PARAPHRASE of X (same facts, reworded) -> high similarity, clears 0.7
  U   an UNRELATED control item (bug ticket) -> to measure the 0.7 threshold

Sequence:
  1. Score X, Xp, U cold (no feedback yet).
  2. Human OVERRIDES X up to 9.0 with transferable reasoning.
  3. Re-score Xp. If retrieval + injection work, Xp rises toward 9.0.

The items are fixed below BEFORE any result is seen -- nothing is reverse-engineered.

Usage:
    BASE_URL=http://127.0.0.1:8000 python scripts/demo_injection_test.py
"""

import os

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
RUBRIC = "sales-call-v2"

# --- Fixed items (chosen before seeing any score) ---------------------------

# X: reads modest -- short, no demo, no pricing -- but uncovers a quantified
# pain point and earns a warm intro to the economic buyer. Should score low cold.
X = (
    "A 20-minute call with the head of operations at a regional logistics company. "
    "The conversation stayed high-level -- no product demo, no pricing discussed -- "
    "but they described a recurring fulfillment bottleneck in detail and agreed to "
    "introduce us to their VP of Supply Chain next week."
)

# Xp: a close paraphrase of X -- same facts, reworded. Should be ~0.9 similar to X.
XP = (
    "A brief 20-minute conversation with a regional logistics company's operations "
    "lead. We did not demo the product or talk pricing, but they walked us through a "
    "persistent fulfillment bottleneck and offered to connect us with their VP of "
    "Supply Chain the following week."
)

# U: unrelated control -- an engineering support ticket. Used only to measure how
# far an UNRELATED pair sits from the related pair, to judge the 0.7 threshold.
U = (
    "Resolved a P2 support ticket: a customer's CSV export was timing out on large "
    "datasets. Traced it to a missing database index, added the index, and confirmed "
    "the export completed in under 3 seconds."
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
    print(f"\n  {label}")
    print(f"    Primary {res.get('primary_score')} | "
          f"Auditor {res.get('auditor_score')} (independent) | "
          f"gap {res.get('disagreement')} | path {res.get('path')}")
    print(f"    Final score : {res.get('final_score')} "
          f"(human review: {res.get('requires_human_review')})")


def main() -> None:
    with httpx.Client() as client:
        print("=" * 70)
        print("MIZAAN -- RAG injection test (proving the learning-loop link)")
        print("=" * 70)

        print("\n[1] Score X (modest logistics call) -- cold, expect a LOW score")
        x = score(client, X, "Regional logistics ops call")
        show("X (cold)", x)

        print("\n[2] Score Xp (paraphrase of X) -- cold BASELINE, before any feedback")
        xp_before = score(client, XP, "Logistics ops call (paraphrase)")
        show("Xp (before)", xp_before)

        print("\n[3] Score U (unrelated bug ticket) -- control for threshold measurement")
        u = score(client, U, "CSV export timeout fix")
        show("U (control)", u)

        print("\n[4] Human OVERRIDES X up to 9.0 with transferable reasoning")
        feedback(
            client,
            x["id"],
            "OVERRIDDEN",
            9.0,
            "Surfacing a quantified, recurring operational pain point and securing a "
            "warm introduction to the economic buyer (VP of Supply Chain) is "
            "high-impact early-stage progress -- far more valuable than a polished "
            "demo with no next step. Reward this kind of strategic groundwork.",
        )
        print("    stored override: X -> 9.0 (re-embedded with the reasoning)")

        print("\n[5] Re-score Xp -- RAG should now retrieve X's correction and inject it")
        xp_after = score(client, XP, "Logistics ops call (paraphrase)")
        show("Xp (after learning)", xp_after)

        # --- Result -------------------------------------------------------
        print("\n" + "=" * 70)
        print("RESULT")
        print("=" * 70)
        before = xp_before.get("final_score") or 0
        after = xp_after.get("final_score") or 0
        delta = round(after - before, 2)
        print(f"  Xp final score: {before}  ->  {after}   (delta {delta:+})")
        print(f"  X cold score (for headroom check): {x.get('final_score')}")
        if delta > 0.3:
            print("  PASS: injection link works -- a human correction on X moved a")
            print("        similar item Xp upward, with NO retraining (RAG only).")
        else:
            print("  INCONCLUSIVE: Xp did not rise. Check (a) X cold score had headroom,")
            print("        (b) the X<->Xp similarity cleared the 0.7 retrieval floor,")
            print("        (c) the retrieved text reached the scorer prompt.")
        print("\n  IDs for DB inspection (similarity + retrieval candidates):")
        print(f"    X  = {x.get('id')}")
        print(f"    Xp = {xp_after.get('id')}")
        print(f"    U  = {u.get('id')}")


if __name__ == "__main__":
    main()
