"""Phase 3 demo: corrections cluster -> rubric amendment -> policy learning.

The full-circle story this proves, against a running API:

  1. Three human corrections teach the SAME lesson on different items
     (no demo, but senior stakeholder + strategic pain + earned next step
     => high impact). Instance-level RAG already applies each one.
  2. detect: the corrections cluster by embedding; the LLM drafts ONE new
     scoring criterion that would have made them unnecessary.
  3. A human APPROVES: rubric v+1 is created — BOTH agents render the new
     criterion from now on — and the promoted exemplars are retired from
     retrieval (the lesson moved from instances into policy).
  4. Re-score: the result records rubric_version v+1 and retrieves 0
     exemplars; the lesson now arrives through the rubric, not RAG.

Assumes the dev DB already holds one such correction (C, the manufacturing
CFO call from the cross-domain demo). Adds two more (E, F), then runs
detect -> approve -> re-score.

Usage:
    BASE_URL=http://127.0.0.1:8000 python scripts/demo_promotion.py
"""

import os

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
RUBRIC = "sales-call-v2"

# Same abstract pattern as C (manufacturing CFO call), different domains.
E = (
    "A 25-minute introductory call with the COO of a regional retail bank. No "
    "demo and no pricing -- but the COO candidly walked us through how manual "
    "loan-document review is their biggest operational drag, and agreed to pull "
    "in their head of lending operations for a working session."
)
F = (
    "A 30-minute first conversation with the operations director of a mid-size "
    "cargo airline. We showed nothing and never discussed cost; the director "
    "detailed how crew-scheduling disruptions cascade into millions in delay "
    "costs, and offered to set up a session with their network-planning team."
)
LESSON = (
    "Early calls that skip the demo but get a senior decision-maker to surface "
    "a strategic, quantified pain point and commit to a working session with "
    "the right team are high-impact groundwork -- reward uncovering real pain "
    "and earning senior access, not demos and pricing talk."
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


def override(client: httpx.Client, sid: str) -> None:
    r = client.post(
        f"{BASE}/api/v1/feedback/",
        json={
            "scoring_result_id": sid,
            "decision": "OVERRIDDEN",
            "adjusted_score": 9.0,
            "reasoning": LESSON,
        },
        timeout=120,
    )
    r.raise_for_status()


def show(label: str, res: dict) -> None:
    print(
        f"  {label}: warm {res.get('primary_score')} | cold "
        f"{res.get('primary_cold_score')} | auditor {res.get('auditor_score')} | "
        f"path {res.get('path')} | rubric v{res.get('rubric_version')} | "
        f"exemplars {len(res.get('retrieved_examples') or [])}"
    )


def main() -> None:
    with httpx.Client() as client:
        print("=" * 70)
        print("MIZAAN -- Phase 3: corrections -> rubric amendment -> policy")
        print("=" * 70)

        print("\n[1] Two more same-lesson corrections (bank COO, airline ops)")
        e = score(client, E, "Bank COO call")
        show("E (cold-scored)", e)
        override(client, e["id"])
        print("    override: E -> 9.0")
        f = score(client, F, "Airline ops director call")
        show("F (cold-scored)", f)
        override(client, f["id"])
        print("    override: F -> 9.0  (3 same-lesson corrections now stored)")

        print("\n[2] Detect: cluster corrections, draft amendment")
        r = client.post(
            f"{BASE}/api/v1/patterns/amendments/detect",
            json={"rubric_slug": RUBRIC},
            timeout=300,
        )
        r.raise_for_status()
        drafts = r.json()
        if not drafts:
            print("    no draft produced (cluster below threshold?) -- stopping")
            return
        d = drafts[0]
        print(f"    DRAFT amendment on '{d['target_dimension']}' "
              f"(cluster of {d['cluster_size']}):")
        print(f"      + {d['amendment_text']}")
        print(f"      rationale: {d['rationale']}")

        print("\n[3] Human APPROVES -> rubric v+1, exemplars retired")
        r = client.post(
            f"{BASE}/api/v1/patterns/amendments/{d['id']}/approve", timeout=120
        )
        r.raise_for_status()
        approved = r.json()
        print(f"    status {approved['status']} -> rubric version "
              f"{approved['approved_version']}; "
              f"{len(approved['correction_ids'])} exemplars retired")

        print("\n[4] Re-score a similar item: lesson now arrives via the RUBRIC")
        d2 = score(
            client,
            "A 30-minute first call with the IT director of a regional hospital "
            "network. We did not show the product or discuss cost. Instead, the "
            "director described in detail the compliance and data-integration "
            "challenges they face across patient record systems, and asked us to "
            "scope a follow-up workshop with their information-security team.",
            "Hospital IT director call (post-promotion)",
        )
        show("D (post-promotion)", d2)

        print("\n" + "=" * 70)
        print("RESULT")
        print("=" * 70)
        print(f"  rubric version on the new score : {d2.get('rubric_version')}")
        print(f"  exemplars retrieved             : "
              f"{len(d2.get('retrieved_examples') or [])} (promoted ones retired)")
        print("  If rubric version bumped and exemplars dropped to 0, the lesson")
        print("  moved from instance memory (RAG) into policy (the rubric) --")
        print("  and BOTH agents now apply it.")


if __name__ == "__main__":
    main()
