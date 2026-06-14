"""Offline analyses for Section 6 — deterministic, no API calls.

Three analyses over the stored (warm, cold, auditor) triples from runs 1-3,
phase C (instance-learning phase: exemplars present, rubric still v1, so
attribution is actively exercised):

  1. Attribution confusion matrix — router verdict vs protocol ground truth.
  2. tau_c sensitivity sweep — learning-recall vs false-attribution as the
     cold-agreement threshold varies.
  3. Warm-gap-only baseline re-routing — escalation under the counterfactual
     router vs a dual-agent baseline that routes on the warm gap alone.

Ground truth (EVAL_PROTOCOL section 2): a warm-vs-auditor gap counts as
"learning" iff the item is HOLDOUT_SIM (paired to a corrected item) AND its
learning delta (warm - cold) moves toward the override (> 0); else "error".

Output: eval/results/offline_analyses.json + printed tables.

Usage:
    python scripts/eval_offline.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _resolve_results() -> Path:
    """Locate the results dir in both the source repo and the standalone
    artifact release (where results/ is a sibling of scripts/)."""
    env = os.environ.get("MIZAAN_RESULTS")
    if env:
        return Path(env)
    sib = Path(__file__).resolve().parent.parent / "results"
    if (sib / "run_1").exists() or (sib / "aggregate.json").exists():
        return sib
    return (
        Path(__file__).resolve().parents[2]
        / "Refrences/DocBase/PublishPaper/eval/results"
    )


RESULTS = _resolve_results()
RUNS = [1, 2, 3]

TAU = 1.0  # agreement threshold (warm gap)
TAU_C = 0.75  # cold-agreement threshold (as configured in the runs)
LEARNING_DELTA_EPS = 1e-9  # delta > 0 counts as "moved toward the (upward) override"


def load_phase_pooled(phase: str) -> list[dict]:
    pooled = []
    for r in RUNS:
        p = RESULTS / f"run_{r}" / f"phase_{phase}.jsonl"
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rec = json.loads(line)
                    rec["_run"] = r
                    pooled.append(rec)
    return pooled


def warm_gap(rec: dict) -> float:
    return abs(rec["primary_warm"] - rec["auditor"])


def cold_gap(rec: dict) -> float:
    return abs(rec["primary_cold"] - rec["auditor"])


def learning_delta(rec: dict) -> float:
    return rec["primary_warm"] - rec["primary_cold"]


def is_true_learning(rec: dict) -> bool:
    """Protocol ground truth: HOLDOUT_SIM with delta moving toward override."""
    return (
        rec.get("split") == "HOLDOUT_SIM" and learning_delta(rec) > LEARNING_DELTA_EPS
    )


# ---------------------------------------------------------------------------
# 1. Attribution confusion matrix (gapped phase-C cases)
# ---------------------------------------------------------------------------


def attribution_matrix(recs: list[dict]) -> dict:
    gapped = [r for r in recs if warm_gap(r) > TAU]
    cells = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}
    examples = {"fn": []}
    for r in gapped:
        gt_learning = is_true_learning(r)
        router_learning = cold_gap(r) <= TAU_C  # == path AUTO_ACCEPT_LEARNED
        if gt_learning and router_learning:
            cells["tp"] += 1
        elif gt_learning and not router_learning:
            cells["fn"] += 1
            if len(examples["fn"]) < 6:
                examples["fn"].append(
                    {
                        "run": r["_run"],
                        "id": r["item_id"],
                        "domain": r["domain"],
                        "warm": r["primary_warm"],
                        "cold": r["primary_cold"],
                        "auditor": r["auditor"],
                        "cold_gap": round(cold_gap(r), 2),
                    }
                )
        elif not gt_learning and router_learning:
            cells["fp"] += 1
        else:
            cells["tn"] += 1
    tp, fn, fp = cells["tp"], cells["fn"], cells["fp"]
    learning_total = tp + fn
    return {
        "gapped_cases": len(gapped),
        "cells": cells,
        "learning_recall": round(tp / learning_total, 4) if learning_total else None,
        "attribution_miss_rate": (
            round(fn / learning_total, 4) if learning_total else None
        ),
        "false_attribution_count": fp,
        "fn_examples": examples["fn"],
        "note": (
            "FN = real learning the router escalated (cold gap > tau_c because the "
            "auditor scores the unpolished item harder than the cold primary). "
            "This is the auditor-bias / tau_c interaction."
        ),
    }


# ---------------------------------------------------------------------------
# 2. tau_c sensitivity sweep
# ---------------------------------------------------------------------------


def tau_c_sweep(recs: list[dict]) -> dict:
    gapped = [r for r in recs if warm_gap(r) > TAU]
    learning = [r for r in gapped if is_true_learning(r)]  # should be auto-accepted
    not_learning = [r for r in gapped if not is_true_learning(r)]  # should be escalated
    grid = [round(0.25 * i, 2) for i in range(0, 13)]  # 0.00 .. 3.00
    rows = []
    for tc in grid:
        recl = (
            sum(1 for r in learning if cold_gap(r) <= tc) / len(learning)
            if learning
            else None
        )
        fattr = (
            sum(1 for r in not_learning if cold_gap(r) <= tc) / len(not_learning)
            if not_learning
            else None
        )
        rows.append(
            {
                "tau_c": tc,
                "learning_recall": round(recl, 4) if recl is not None else None,
                "false_attribution": round(fattr, 4) if fattr is not None else None,
            }
        )
    # cold-gap distribution among true-learning gapped cases (why 0.75 misses)
    cgs = sorted(round(cold_gap(r), 2) for r in learning)
    return {
        "gapped_learning_n": len(learning),
        "gapped_not_learning_n": len(not_learning),
        "configured_tau_c": TAU_C,
        "sweep": rows,
        "true_learning_cold_gaps": cgs,
        "true_learning_cold_gap_median": cgs[len(cgs) // 2] if cgs else None,
    }


# ---------------------------------------------------------------------------
# 3. Warm-gap-only baseline re-routing
# ---------------------------------------------------------------------------


def baseline_reroute(recs: list[dict], tau_c_alt: float | None = None) -> dict:
    n = len(recs)
    # (a) dual-agent baseline: escalate iff warm gap > tau
    base_esc = sum(1 for r in recs if warm_gap(r) > TAU)
    # (b) counterfactual @ configured tau_c: escalate iff warm gap>tau AND cold gap>tau_c
    cf_esc = sum(1 for r in recs if warm_gap(r) > TAU and cold_gap(r) > TAU_C)
    out = {
        "n": n,
        "baseline_warm_only": {
            "escalations": base_esc,
            "escalation_rate": round(base_esc / n, 4),
        },
        "counterfactual_tau_c_0.75": {
            "escalations": cf_esc,
            "escalation_rate": round(cf_esc / n, 4),
            "reviews_saved_vs_baseline": base_esc - cf_esc,
        },
    }
    if tau_c_alt is not None:
        alt_esc = sum(1 for r in recs if warm_gap(r) > TAU and cold_gap(r) > tau_c_alt)
        out[f"counterfactual_tau_c_{tau_c_alt}"] = {
            "escalations": alt_esc,
            "escalation_rate": round(alt_esc / n, 4),
            "reviews_saved_vs_baseline": base_esc - alt_esc,
        }
    return out


def main() -> None:
    phase_c = load_phase_pooled("C")
    result = {
        "phase": "C (instance learning, pooled runs 1-3)",
        "n_records": len(phase_c),
        "tau": TAU,
        "tau_c_configured": TAU_C,
        "attribution_matrix": attribution_matrix(phase_c),
        "tau_c_sweep": tau_c_sweep(phase_c),
    }
    # pick a calibrated tau_c at the median true-learning cold gap, for the baseline cmp
    med = result["tau_c_sweep"]["true_learning_cold_gap_median"]
    result["baseline_reroute"] = baseline_reroute(phase_c, tau_c_alt=med)

    out = RESULTS / "offline_analyses.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {out}\n")

    am = result["attribution_matrix"]
    print("=== 1. ATTRIBUTION (gapped phase-C cases, pooled n=3) ===")
    print(f"  gapped cases: {am['gapped_cases']}  cells {am['cells']}")
    print(
        f"  learning recall: {am['learning_recall']}  "
        f"attribution-miss rate: {am['attribution_miss_rate']}  "
        f"false-attributions: {am['false_attribution_count']}"
    )
    sw = result["tau_c_sweep"]
    print(
        f"\n=== 2. TAU_C SWEEP (learning n={sw['gapped_learning_n']}, "
        f"not-learning n={sw['gapped_not_learning_n']}) ==="
    )
    print("  tau_c  recall  false_attr")
    for row in sw["sweep"]:
        if row["tau_c"] <= 2.0:
            print(
                f"  {row['tau_c']:.2f}   {row['learning_recall']}   {row['false_attribution']}"
            )
    print(f"  true-learning cold-gap median: {sw['true_learning_cold_gap_median']}")
    br = result["baseline_reroute"]
    print("\n=== 3. BASELINE RE-ROUTING (phase C) ===")
    for k, v in br.items():
        if not isinstance(v, dict):
            continue
        saved = (
            f", saved {v['reviews_saved_vs_baseline']}"
            if "reviews_saved_vs_baseline" in v
            else ""
        )
        print(
            f"  {k}: esc_rate {v['escalation_rate']} "
            f"({v['escalations']}/{br['n']}){saved}"
        )


if __name__ == "__main__":
    main()
