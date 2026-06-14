"""Mizaan evaluation runner — executes the pre-registered protocol.

Implements EVAL_PROTOCOL.md (Refrences/DocBase/PublishPaper/eval/) phase by
phase against a running API. Every per-item record and every telemetry
snapshot is written to disk; the paper may cite ONLY numbers derived from
these files.

Dataset format (eval/datasets/{swe,re}.jsonl), one JSON object per line:
    {"id": "swe-001", "domain": "swe", "source": "github:...",
     "text": "...", "quality_band": "high|med|low|unknown",
     "split": "CORRECT|HOLDOUT_SIM|NEUTRAL", "paired_with": "swe-007"|null}

Usage (run phases in order; fresh DB per run number):
    python scripts/eval_runner.py --run 1 --phase A   # cold baseline (all items)
    python scripts/eval_runner.py --run 1 --phase B   # apply override rules
    python scripts/eval_runner.py --run 1 --phase C   # re-score holdouts
    python scripts/eval_runner.py --run 1 --phase D   # detect + interactive approve
    python scripts/eval_runner.py --run 1 --phase E   # post-promotion re-score
    python scripts/eval_runner.py --run 1 --phase F   # canary (bad lesson)
    python scripts/eval_runner.py --run 1 --summarize # aggregate this run

Environment:
    BASE_URL (default http://127.0.0.1:8000)
    EVAL_DIR (default <repo>/Refrences/DocBase/PublishPaper/eval)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean, median

import httpx

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
# Bounded concurrency for scoring phases (A/C/E). Scoring only READS the
# feedback store (overrides are written in phase B, promotion in D), so item
# order does not affect any result — concurrency is a pure throughput win.
# Added from run 2 onward; run 1 was sequential (see EVAL_PROTOCOL Amendments).
EVAL_WORKERS = int(os.environ.get("EVAL_WORKERS", "5"))
REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = Path(os.environ.get("EVAL_DIR", REPO_ROOT / "Refrences/DocBase/PublishPaper/eval"))
DATASET_DIR = EVAL_DIR / "datasets"
RESULTS_DIR = EVAL_DIR / "results"

RUBRICS = {
    "swe": {
        "slug": "swe-workitem-v1",
        "name": "Software Work Item Quality v1",
        "dimensions": [
            {"name": "Problem clarity", "weight": 0.3,
             "description": "Is the problem or goal stated clearly and unambiguously?",
             "scoring_criteria": ["States what is wrong or needed", "Unambiguous scope"]},
            {"name": "Reproducibility or acceptance criteria", "weight": 0.3,
             "description": "Bugs: reproduction steps. Stories: testable acceptance criteria.",
             "scoring_criteria": ["Steps or criteria present", "Verifiable outcomes"]},
            {"name": "Impact articulation", "weight": 0.25,
             "description": "Who is affected and how much does it matter to them?",
             "scoring_criteria": ["Affected users identified", "Business or user impact stated"]},
            {"name": "Scope realism", "weight": 0.15,
             "description": "Is the item appropriately sized and free of hidden scope?",
             "scoring_criteria": ["Single coherent change", "Dependencies acknowledged"]},
        ],
    },
    "re": {
        "slug": "re-listing-v1",
        "name": "Real Estate Listing Quality v1",
        "dimensions": [
            {"name": "Completeness", "weight": 0.3,
             "description": "Essential facts: type, size, location, price terms, amenities.",
             "scoring_criteria": ["Core facts present", "No critical omissions"]},
            {"name": "Appeal", "weight": 0.25,
             "description": "Compelling, professional writing with concrete imagery.",
             "scoring_criteria": ["Vivid but factual language", "Professional tone"]},
            {"name": "Target audience fit", "weight": 0.25,
             "description": "Speaks to the plausible buyer's actual decision factors.",
             "scoring_criteria": ["Investment/lifestyle framing fits the segment"]},
            {"name": "Credibility", "weight": 0.2,
             "description": "Honest, verifiable claims; discloses limitations.",
             "scoring_criteria": ["No inflated claims", "Limitations disclosed"]},
        ],
    },
}

# Pre-registered override rules (EVAL_PROTOCOL.md section 2).
RULES = {
    "S1": {
        "domain": "swe", "score": 9.0,
        "reasoning": "Clearly identifying the affected user population and the "
                     "business impact matters more than writing polish. Reward "
                     "impact articulation over polish.",
    },
    "R1": {
        "domain": "re", "score": 8.5,
        "reasoning": "Honest disclosure of limitations (facing, age, fees) signals "
                     "credibility and should be rewarded, not penalized. Reward "
                     "credibility and honest disclosure.",
    },
    # Canary-only BAD rule (phase F). Excluded from C1-C3 analysis.
    "X1": {
        "domain": "re", "score": 9.5,
        "reasoning": "Long listings deserve top scores.",
    },
}


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------


def load_items() -> list[dict]:
    items = []
    for name in ("swe", "re"):
        path = DATASET_DIR / f"{name}.jsonl"
        if not path.exists():
            print(f"!! missing dataset {path} — prepare datasets first")
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    items.append(json.loads(line))
    return items


def out_dir(run: int) -> Path:
    d = RESULTS_DIR / f"run_{run}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"   wrote {path}")


def append_jsonl(path: Path, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def ensure_rubrics(client: httpx.Client) -> None:
    existing = {r.get("slug") for r in client.get(f"{BASE}/api/v1/rubrics/").json()}
    for spec in RUBRICS.values():
        if spec["slug"] in existing:
            continue
        r = client.post(
            f"{BASE}/api/v1/rubrics/",
            json={
                "name": spec["name"],
                "slug": spec["slug"],
                "description": spec["name"],
                "dimensions": spec["dimensions"],
            },
            timeout=60,
        )
        r.raise_for_status()
        print(f"   created rubric {spec['slug']}")


# Transient statuses worth retrying. Our API wraps an upstream LLM
# RateLimitError as a 500, so 500 is included (rate-limited models such as
# gpt-4.1 at 30k TPM need this); 429/502/503 are the usual transients.
_RETRY_STATUS = {429, 500, 502, 503}
_MAX_RETRIES = 5


def _post_retrying(client: httpx.Client, url: str, payload: dict, timeout: float) -> dict:
    """POST with exponential backoff on transient (rate-limit) failures."""
    last_status = None
    for attempt in range(_MAX_RETRIES):
        r = client.post(url, json=payload, timeout=timeout)
        if r.status_code not in _RETRY_STATUS:
            r.raise_for_status()
            return r.json()
        last_status = r.status_code
        # Backoff: 3, 6, 12, 24s — long enough to clear a per-minute TPM reset.
        time.sleep(3 * (2**attempt))
    raise httpx.HTTPStatusError(
        f"giving up after {_MAX_RETRIES} retries (last status {last_status})",
        request=r.request,
        response=r,
    )


def score_item(client: httpx.Client, item: dict) -> dict:
    return _post_retrying(
        client,
        f"{BASE}/api/v1/scoring/score",
        {
            "work_item_description": item["text"],
            "work_item_type": item["domain"],
            "work_item_title": item["id"],
            "rubric_slug": RUBRICS[item["domain"]]["slug"],
            "external_id": item["id"],
        },
        timeout=600,
    )


def submit_override(client: httpx.Client, scoring_id: str, rule_key: str) -> None:
    rule = RULES[rule_key]
    _post_retrying(
        client,
        f"{BASE}/api/v1/feedback/",
        {
            "scoring_result_id": scoring_id,
            "decision": "OVERRIDDEN",
            "adjusted_score": rule["score"],
            "reasoning": rule["reasoning"],
        },
        timeout=120,
    )


def telemetry(client: httpx.Client) -> dict:
    return client.get(f"{BASE}/api/v1/analytics/telemetry", timeout=60).json()


def record_for(item: dict, res: dict, phase: str) -> dict:
    return {
        "phase": phase,
        "item_id": item["id"],
        "domain": item["domain"],
        "split": item.get("split"),
        "paired_with": item.get("paired_with"),
        "scoring_id": res.get("id"),
        "primary_warm": res.get("primary_score"),
        "primary_cold": res.get("primary_cold_score"),
        "auditor": res.get("auditor_score"),
        "disagreement": res.get("disagreement"),
        "path": res.get("path"),
        "learning_explained": res.get("learning_explained"),
        "spot_check": res.get("spot_check"),
        "final": res.get("final_score"),
        "requires_human_review": res.get("requires_human_review"),
        "rubric_version": res.get("rubric_version"),
        "exemplars_used": len(res.get("retrieved_examples") or []),
        "latency_ms": res.get("latency_ms"),
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "ts": time.time(),
    }


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------


def phase_score(run: int, phase: str, items: list[dict]) -> None:
    """Score items with bounded concurrency; append records, snapshot telemetry.

    Concurrency is safe within a scoring phase: scoring READS the feedback
    store but never writes to it, so item order does not affect any result.
    A failed item is left un-recorded so a re-run retries it (resumable).
    """
    d = out_dir(run)
    log = d / f"phase_{phase}.jsonl"
    done = set()
    if log.exists():  # resumable
        with open(log, encoding="utf-8") as fh:
            done = {json.loads(line)["item_id"] for line in fh if line.strip()}

    todo = [item for item in items if item["id"] not in done]
    write_lock = threading.Lock()
    progress = {"n": len(done)}
    total = len(items)

    with httpx.Client() as client:
        ensure_rubrics(client)

        def work(item: dict) -> None:
            try:
                res = score_item(client, item)
            except Exception as exc:  # noqa: BLE001 — keep the phase alive
                with write_lock:
                    print(f"   !! {item['id']} FAILED: {exc} (retry on re-run)")
                return
            rec = record_for(item, res, phase)
            with write_lock:
                append_jsonl(log, rec)
                progress["n"] += 1
                print(f"   [{progress['n']}/{total}] {item['id']}: "
                      f"warm {rec['primary_warm']} cold {rec['primary_cold']} "
                      f"aud {rec['auditor']} -> {rec['path']}")

        with ThreadPoolExecutor(max_workers=EVAL_WORKERS) as pool:
            list(pool.map(work, todo))

        write_json(d / f"telemetry_after_{phase}.json", telemetry(client))


def phase_a(run: int) -> None:
    print("[A] cold baseline — scoring ALL items (feedback store must be empty)")
    phase_score(run, "A", load_items())


def phase_b(run: int) -> None:
    print("[B] applying pre-registered override rules to CORRECT items")
    d = out_dir(run)
    scored = {}
    with open(d / "phase_A.jsonl", encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            scored[rec["item_id"]] = rec
    items = {i["id"]: i for i in load_items()}
    log = d / "phase_B.jsonl"
    with httpx.Client() as client:
        for item_id, rec in scored.items():
            item = items.get(item_id)
            if not item or item.get("split") != "CORRECT":
                continue
            rule_key = "S1" if item["domain"] == "swe" else "R1"
            submit_override(client, rec["scoring_id"], rule_key)
            append_jsonl(log, {"item_id": item_id, "rule": rule_key,
                               "scoring_id": rec["scoring_id"], "ts": time.time()})
            print(f"   override {item_id} via rule {rule_key}")
        write_json(d / "telemetry_after_B.json", telemetry(client))


def phase_c(run: int) -> None:
    print("[C] instance learning — re-scoring HOLDOUT_SIM + NEUTRAL")
    items = [i for i in load_items() if i.get("split") in ("HOLDOUT_SIM", "NEUTRAL")]
    phase_score(run, "C", items)


def phase_d(run: int) -> None:
    print("[D] promotion — detect, then interactive human approve/reject")
    d = out_dir(run)
    decisions = []
    with httpx.Client() as client:
        for spec in RUBRICS.values():
            r = client.post(
                f"{BASE}/api/v1/patterns/amendments/detect",
                json={"rubric_slug": spec["slug"]},
                timeout=600,
            )
            r.raise_for_status()
            for draft in r.json():
                print("\n" + "=" * 60)
                print(f"DRAFT on '{draft['target_dimension']}' "
                      f"(cluster of {draft['cluster_size']}, rubric {spec['slug']}):")
                print(f"  + {draft['amendment_text']}")
                print(f"  rationale: {draft['rationale']}")
                choice = input("approve? [y/N]: ").strip().lower()
                action = "approve" if choice == "y" else "reject"
                rr = client.post(
                    f"{BASE}/api/v1/patterns/amendments/{draft['id']}/{action}",
                    timeout=120,
                )
                rr.raise_for_status()
                decisions.append({"draft": draft, "decision": action, "ts": time.time()})
                print(f"  -> {action.upper()}")
        write_json(d / "phase_D_decisions.json", decisions)
        write_json(d / "telemetry_after_D.json", telemetry(client))


def phase_e(run: int) -> None:
    print("[E] post-promotion — re-scoring HOLDOUT_SIM + NEUTRAL")
    items = [i for i in load_items() if i.get("split") in ("HOLDOUT_SIM", "NEUTRAL")]
    phase_score(run, "E", items)


def phase_f(run: int) -> None:
    print("[F] canary — injecting BAD rule X1 on a small RE subset, then re-scoring")
    items = [i for i in load_items()
             if i["domain"] == "re" and i.get("split") == "NEUTRAL"][:10]
    if not items:
        print("   no RE NEUTRAL items available")
        return
    d = out_dir(run)
    bad_set = items[:5]
    probe_set = items  # re-score all 10; the 5 uncorrected are probes
    with httpx.Client() as client:
        # score + bad-override the first 5
        for item in bad_set:
            res = score_item(client, item)
            submit_override(client, res["id"], "X1")
            append_jsonl(d / "phase_F.jsonl",
                         {**record_for(item, res, "F-inject"), "rule": "X1"})
            print(f"   injected bad lesson on {item['id']}")
        # re-score probes; spot-checked AUTO_ACCEPT(_LEARNED) cases would be
        # reviewed by an honest human -> here, any learned-accept moved toward
        # 9.5 by X1 counts as would-be-overturned (recorded for analysis).
        for item in probe_set:
            res = score_item(client, item)
            append_jsonl(d / "phase_F.jsonl", record_for(item, res, "F-probe"))
        write_json(d / "telemetry_after_F.json", telemetry(client))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def _dist(values: list[float]) -> dict:
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "mean": round(mean(vals), 3),
            "median": round(median(vals), 3),
            "min": round(min(vals), 3), "max": round(max(vals), 3)}


def summarize(run: int) -> None:
    d = out_dir(run)
    summary: dict = {"run": run}
    for phase in ("A", "C", "E"):
        path = d / f"phase_{phase}.jsonl"
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as fh:
            recs = [json.loads(line) for line in fh if line.strip()]
        by_split: dict = {}
        for split in ("CORRECT", "HOLDOUT_SIM", "NEUTRAL", None):
            rs = [r for r in recs if r.get("split") == split]
            if not rs:
                continue
            by_split[str(split)] = {
                "disagreement": _dist([r["disagreement"] for r in rs]),
                "learning_delta": _dist([
                    (r["primary_warm"] - r["primary_cold"])
                    if r["primary_warm"] is not None and r["primary_cold"] is not None
                    else None for r in rs]),
                "paths": {p: sum(1 for r in rs if r["path"] == p)
                          for p in ("AUTO_ACCEPT", "AUTO_ACCEPT_LEARNED", "HUMAN_REQUIRED")},
                "cold": _dist([r["primary_cold"] for r in rs]),
                "warm": _dist([r["primary_warm"] for r in rs]),
                "auditor": _dist([r["auditor"] for r in rs]),
                "exemplars": _dist([r["exemplars_used"] for r in rs]),
            }
        summary[f"phase_{phase}"] = by_split
    write_json(d / "summary.json", summary)
    print(json.dumps(summary, indent=2)[:2000])


# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--phase", choices=list("ABCDEF"), default=None)
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()

    if args.summarize:
        summarize(args.run)
        return
    if not args.phase:
        parser.error("--phase or --summarize required")
    {"A": phase_a, "B": phase_b, "C": phase_c,
     "D": phase_d, "E": phase_e, "F": phase_f}[args.phase](args.run)


if __name__ == "__main__":
    sys.exit(main())
