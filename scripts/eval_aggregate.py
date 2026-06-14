"""Aggregate eval runs 1-3 into the numbers Section 6 cites.

Pure analysis over committed per-item records (no API calls). Produces
eval/results/aggregate.json and prints the headline tables. Every number the
paper reports must come from this file.

Reports per metric: each run's value + pooled mean and sample std-dev (n=3),
so the paper shows distributions, not point estimates.

Usage:
    python scripts/eval_aggregate.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from statistics import mean, stdev


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


def load_phase(run: int, phase: str) -> list[dict]:
    p = RESULTS / f"run_{run}" / f"phase_{phase}.jsonl"
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def msd(values: list[float]) -> dict:
    """Mean and sample std-dev across runs (n>=2) — the cross-run spread."""
    vals = [v for v in values if v is not None]
    if not vals:
        return {"values": [], "mean": None, "sd": None}
    sd = round(stdev(vals), 4) if len(vals) > 1 else 0.0
    return {
        "values": [round(v, 4) for v in vals],
        "mean": round(mean(vals), 4),
        "sd": sd,
    }


def delta(rec: dict) -> float | None:
    w, c = rec.get("primary_warm"), rec.get("primary_cold")
    return None if w is None or c is None else w - c


def per_run_metric(phase: str, fn) -> list:
    """Apply fn(records) to each run's phase records; return per-run values."""
    return [fn(load_phase(r, phase)) for r in RUNS if load_phase(r, phase)]


def agreement_rate(recs: list[dict], thr: float = 1.0) -> float:
    g = [r["disagreement"] for r in recs if r["disagreement"] is not None]
    return sum(1 for x in g if x <= thr) / len(g)


def mean_gap(recs: list[dict]) -> float:
    g = [r["disagreement"] for r in recs if r["disagreement"] is not None]
    return mean(g)


def split_delta(recs: list[dict], split: str, domain: str | None = None) -> float:
    rs = [
        r
        for r in recs
        if r.get("split") == split and (domain is None or r.get("domain") == domain)
    ]
    ds = [delta(r) for r in rs]
    ds = [d for d in ds if d is not None]
    return mean(ds) if ds else 0.0


def split_mean(recs: list[dict], key: str, split: str, domain: str) -> float:
    rs = [r for r in recs if r.get("split") == split and r.get("domain") == domain]
    vs = [r[key] for r in rs if r.get(key) is not None]
    return mean(vs) if vs else 0.0


def exemplars(recs: list[dict], split: str, domain: str) -> int:
    rs = [r for r in recs if r.get("split") == split and r.get("domain") == domain]
    return sum(r.get("exemplars_used", 0) for r in rs)


def agg_delta(phase: str, split: str, domain: str | None = None) -> dict:
    return msd(
        per_run_metric(phase, lambda rs, s=split, d=domain: split_delta(rs, s, d))
    )


def agg_mean(phase: str, key: str, split: str, domain: str) -> dict:
    return msd(
        per_run_metric(
            phase, lambda rs, k=key, s=split, d=domain: split_mean(rs, k, s, d)
        )
    )


def agg_ex(phase: str, split: str, domain: str) -> list:
    return per_run_metric(phase, lambda rs, s=split, d=domain: exemplars(rs, s, d))


def main() -> None:
    agg: dict = {"runs": RUNS, "n": len(RUNS)}

    # --- C1: cold-baseline inter-agent agreement (phase A) ---
    agg["cold_agreement"] = {
        "agreement_rate": msd(per_run_metric("A", agreement_rate)),
        "mean_gap": msd(per_run_metric("A", mean_gap)),
        "warm_eq_cold_violations": per_run_metric(
            "A", lambda rs: sum(1 for r in rs if r["primary_warm"] != r["primary_cold"])
        ),
    }

    # --- C-phase instance learning: SIM vs NEUTRAL deltas, leakage ---
    agg["instance_learning"] = {
        "sim_delta_all": agg_delta("C", "HOLDOUT_SIM"),
        "neutral_delta_all": agg_delta("C", "NEUTRAL"),
        "sim_delta_swe": agg_delta("C", "HOLDOUT_SIM", "swe"),
        "sim_delta_re": agg_delta("C", "HOLDOUT_SIM", "re"),
        "re_neutral_leak": agg_delta("C", "NEUTRAL", "re"),
        "swe_neutral_delta": agg_delta("C", "NEUTRAL", "swe"),
    }

    # --- C3: three-era consolidation on RE HOLDOUT_SIM ---
    eras = {}
    for era, phase in (
        ("pre_learning", "A"),
        ("instance", "C"),
        ("post_promotion", "E"),
    ):
        eras[era] = {
            "warm": agg_mean(phase, "primary_warm", "HOLDOUT_SIM", "re"),
            "cold": agg_mean(phase, "primary_cold", "HOLDOUT_SIM", "re"),
            "auditor": agg_mean(phase, "auditor", "HOLDOUT_SIM", "re"),
            "exemplars": agg_ex(phase, "HOLDOUT_SIM", "re"),
        }
    agg["consolidation_re_sim"] = eras

    # leakage fix: RE NEUTRAL warm across eras
    agg["leakage_re_neutral_warm"] = {
        "pre": agg_mean("A", "primary_warm", "NEUTRAL", "re"),
        "instance": agg_mean("C", "primary_warm", "NEUTRAL", "re"),
        "post_promotion": agg_mean("E", "primary_warm", "NEUTRAL", "re"),
    }

    # --- SWE no-promotion control (E vs C, no rubric change) ---
    agg["swe_sim_no_promotion"] = {
        "instance_warm": agg_mean("C", "primary_warm", "HOLDOUT_SIM", "swe"),
        "post_warm": agg_mean("E", "primary_warm", "HOLDOUT_SIM", "swe"),
        "instance_cold": agg_mean("C", "primary_cold", "HOLDOUT_SIM", "swe"),
        "post_cold": agg_mean("E", "primary_cold", "HOLDOUT_SIM", "swe"),
    }

    # --- promotion: drafts + human decisions across runs ---
    promo = []
    for r in RUNS:
        dp = RESULTS / f"run_{r}" / "phase_D_decisions.json"
        if dp.exists():
            promo.append(json.loads(dp.read_text(encoding="utf-8")))
    agg["promotion_decisions"] = promo

    # --- C4: canary ---
    canary = []
    for r in RUNS:
        recs = load_phase(r, "F")
        probes = [x for x in recs if x.get("phase") == "F-probe"]
        moved = sum(
            1
            for x in probes
            if (delta(x) or 0) > 0.3 and x.get("exemplars_used", 0) > 0
        )
        sc = sum(1 for x in probes if x.get("spot_check"))
        canary.append(
            {"probes": len(probes), "moved_by_bad_lesson": moved, "spot_checked": sc}
        )
    agg["canary"] = canary

    # --- cost: generations + tokens per item (phase A, representative) ---
    cost = []
    for r in RUNS:
        recs = load_phase(r, "A")
        toks = [
            (x.get("input_tokens") or 0) + (x.get("output_tokens") or 0) for x in recs
        ]
        lat = [x.get("latency_ms") or 0 for x in recs]
        cost.append(
            {
                "items": len(recs),
                "mean_tokens": round(mean(toks), 1) if toks else 0,
                "mean_latency_ms": round(mean(lat), 1) if lat else 0,
            }
        )
    agg["cost_phase_a"] = cost

    out = RESULTS / "aggregate.json"
    out.write_text(json.dumps(agg, indent=2), encoding="utf-8")
    print(f"wrote {out}\n")

    # headline print
    ca = agg["cold_agreement"]
    ar, gp = ca["agreement_rate"], ca["mean_gap"]
    print(
        f"COLD AGREEMENT: rate {ar['mean']:.3f}+/-{ar['sd']:.3f} "
        f"| gap {gp['mean']:.3f}+/-{gp['sd']:.3f} | runs {ar['values']}"
    )
    il = agg["instance_learning"]
    lk_il = il["re_neutral_leak"]
    print(
        f"INSTANCE LEARNING: SIM {il['sim_delta_all']['mean']:+.3f} "
        f"vs NEUTRAL {il['neutral_delta_all']['mean']:+.3f} "
        f"| RE-leak {lk_il['mean']:+.3f}+/-{lk_il['sd']:.3f}"
    )
    e = agg["consolidation_re_sim"]
    print("CONSOLIDATION RE-SIM (warm/cold/ex):")
    for era in ("pre_learning", "instance", "post_promotion"):
        ee = e[era]
        print(
            f"  {era:16s} warm {ee['warm']['mean']:.2f} "
            f"cold {ee['cold']['mean']:.2f} ex {ee['exemplars']}"
        )
    lk = agg["leakage_re_neutral_warm"]
    print(
        f"LEAKAGE RE-NEUTRAL warm: pre {lk['pre']['mean']:.2f} "
        f"-> instance {lk['instance']['mean']:.2f} "
        f"-> post {lk['post_promotion']['mean']:.2f}"
    )
    print(
        f"CANARY moved/probes: {[c['moved_by_bad_lesson'] for c in canary]} "
        f"| spot-checked {[c['spot_checked'] for c in canary]}"
    )


if __name__ == "__main__":
    main()
