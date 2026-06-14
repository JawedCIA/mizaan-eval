"""Cross-domain transfer A/B: does a lowered retrieval threshold let a human
correction generalize across DIFFERENT (non-paraphrase) but same-category items?

Earlier we proved the injection mechanism with a near-paraphrase (cosine 0.73).
This proves the harder claim: a correction on item C (one domain) lifts a
genuinely different item D (another domain) — but only once the retrieval floor
is lowered to admit their ~0.6 similarity. The A/B changes ONLY the threshold,
so the threshold is isolated as the cause.

Items are fixed below BEFORE any score is seen — nothing is reverse-engineered.

  C  manufacturing CFO call  (no demo, surfaces ERP/margin pain, earns next step)
  D  hospital IT call        (no demo, surfaces compliance pain, earns next step)
     -> same abstract pattern, different industry/role/pain -> expect cosine ~0.6

Run TWICE:
  1. Server @ 0.7 (default):   python scripts/demo_cross_domain.py
       -> seeds C + override, scores D before & after -> D stays FLAT (0.6 < 0.7)
  2. Restart server @ 0.55, then: RESCORE_D_ONLY=1 python scripts/demo_cross_domain.py
       -> re-scores the SAME D -> D RISES (retrieval now fires)
"""

import os

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
RUBRIC = "sales-call-v2"
RESCORE_D_ONLY = os.environ.get("RESCORE_D_ONLY") == "1"

C = (
    "A 30-minute introductory call with the CFO of a mid-market industrial "
    "equipment manufacturer. There was no product demo and no pricing discussion "
    "-- the CFO was reserved -- but they walked us through how margin erosion from "
    "an aging ERP system is hurting the business, and agreed to set up a working "
    "session with their finance operations team."
)
D = (
    "A 30-minute first call with the IT director of a regional hospital network. We "
    "did not show the product or discuss cost. Instead, the director described in "
    "detail the compliance and data-integration challenges they face across patient "
    "record systems, and asked us to scope a follow-up workshop with their "
    "information-security team."
)
OVERRIDE_REASONING = (
    "Early calls that skip the demo but get a senior decision-maker to candidly "
    "surface a strategic, business-level pain point and commit to a working session "
    "with the right internal team are high-impact groundwork. Reward uncovering real "
    "pain and earning senior access -- not just demos and pricing talk."
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


def feedback(client: httpx.Client, sid: str, adjusted: float, reasoning: str) -> None:
    r = client.post(
        f"{BASE}/api/v1/feedback/",
        json={
            "scoring_result_id": sid,
            "decision": "OVERRIDDEN",
            "adjusted_score": adjusted,
            "reasoning": reasoning,
        },
        timeout=120,
    )
    r.raise_for_status()


def show(label: str, res: dict) -> None:
    print(f"\n  {label}")
    print(f"    Primary {res.get('primary_score')} | "
          f"Auditor {res.get('auditor_score')} (independent) | "
          f"gap {res.get('disagreement')} | path {res.get('path')}")
    print(f"    Final score : {res.get('final_score')} "
          f"(human review: {res.get('requires_human_review')})  id={res.get('id')}")


def main() -> None:
    with httpx.Client() as client:
        print("=" * 70)

        if RESCORE_D_ONLY:
            print("MIZAAN -- cross-domain A/B  [PHASE 2: server lowered to 0.55]")
            print("=" * 70)
            print("\nRe-score D (same item) -- retrieval should now find C's correction")
            d_after = score(client, D, "Hospital IT director call")
            show("D (after, threshold 0.55)", d_after)
            print("\n  Compare this final score to Phase 1's 'D (after, threshold 0.7)'.")
            print("  If it rose, the ONLY thing that changed was the retrieval floor.")
            return

        print("MIZAAN -- cross-domain A/B  [PHASE 1: server at default 0.70]")
        print("=" * 70)

        print("\n[1] Score C (manufacturing CFO call) -- cold")
        c = score(client, C, "Manufacturing CFO call")
        show("C (cold)", c)

        print("\n[2] Score D (hospital IT call) -- cold BASELINE, before any feedback")
        d_before = score(client, D, "Hospital IT director call")
        show("D (baseline)", d_before)

        print("\n[3] Human OVERRIDES C up to 9.0 with a DOMAIN-AGNOSTIC lesson")
        feedback(client, c["id"], 9.0, OVERRIDE_REASONING)
        print("    stored override: C -> 9.0 (re-embedded with the reasoning)")

        print("\n[4] Re-score D at threshold 0.70 -- expect FLAT (C<->D ~0.6 < 0.7)")
        d_after = score(client, D, "Hospital IT director call")
        show("D (after, threshold 0.7)", d_after)

        print("\n" + "=" * 70)
        print("PHASE 1 RESULT (threshold 0.70)")
        print("=" * 70)
        before = d_before.get("final_score") or 0
        after = d_after.get("final_score") or 0
        print(f"  D final score: {before}  ->  {after}   (delta {round(after - before, 2):+})")
        print("  Expect ~flat: at 0.70 the cross-domain pair is below the floor.")
        print("\n  IDs for cosine check:")
        print(f"    C = {c.get('id')}")
        print(f"    D = {d_after.get('id')}")
        print("\n  NEXT: restart the API with RETRIEVAL_SIMILARITY_THRESHOLD=0.55,")
        print("        then run:  RESCORE_D_ONLY=1 python scripts/demo_cross_domain.py")


if __name__ == "__main__":
    main()
