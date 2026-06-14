"""Single-run generalization metrics for a model-transfer pass (phases A-C).

Computes the same headline metrics as ``eval_aggregate`` but for ONE run on a
different model, and assembles a cross-model comparison file. Used for the
model-generalization passes that test whether the findings hold off the frozen
eval model (gpt-4o-mini): gpt-4.1 (run 4) and claude-sonnet-4-6 (run 5). These
passes run phases A-C only (no promotion), so only agreement + instance
learning are measured.

The learning measure is the SEPARATION (SIM - NEUTRAL): the model-invariant
quantity. Absolute lifts shrink on stronger models, but the separation between
genuinely-similar held-out items and unrelated controls is the signal that the
system learned the right thing. Metric definitions are imported from
``eval_aggregate`` so they stay single-sourced with the main n=3 result.

Usage:
    python scripts/eval_generalization.py            # run 5 -> generalization_claude.json
    python scripts/eval_generalization.py --run 4 --label gpt-4.1 \
        --out generalization_gpt41.json              # reproduce the gpt-4.1 pass
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_aggregate import (  # noqa: E402
    RESULTS,
    agreement_rate,
    load_phase,
    mean_gap,
    split_delta,
)

METRIC_KEYS = [
    "agreement_rate",
    "mean_gap",
    "sim_delta",
    "neutral_delta",
    "learning_separation",
    "re_leak",
    "swe_sim",
]


def run_metrics(run: int) -> dict:
    """The 7 headline metrics for a single A-C run."""
    phase_a = load_phase(run, "A")
    phase_c = load_phase(run, "C")
    if not phase_a or not phase_c:
        raise SystemExit(f"run {run}: phase A or C records missing")
    sim = split_delta(phase_c, "HOLDOUT_SIM")
    neu = split_delta(phase_c, "NEUTRAL")
    return {
        "agreement_rate": round(agreement_rate(phase_a), 3),
        "mean_gap": round(mean_gap(phase_a), 3),
        "sim_delta": round(sim, 3),
        "neutral_delta": round(neu, 3),
        "learning_separation": round(sim - neu, 3),
        "re_leak": round(split_delta(phase_c, "NEUTRAL", "re"), 3),
        "swe_sim": round(split_delta(phase_c, "HOLDOUT_SIM", "swe"), 3),
        "n_A": len(phase_a),
        "n_C": len(phase_c),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=int, default=5)
    ap.add_argument("--label", type=str, default="claude-sonnet-4-6")
    ap.add_argument("--out", type=str, default="generalization_claude.json")
    args = ap.parse_args()

    metrics = run_metrics(args.run)

    # Carry forward the prior columns so one file holds the full comparison.
    prior = RESULTS / "generalization_gpt41.json"
    combined: dict = {}
    if prior.exists():
        combined = json.loads(prior.read_text(encoding="utf-8"))
    combined[f"{args.label}_run{args.run}"] = metrics

    out = RESULTS / args.out
    out.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    print(f"wrote {out}\n")

    # Comparison table — learning SEPARATION is the headline row.
    cols = [
        k
        for k in combined
        if isinstance(combined[k], dict) and "learning_separation" in combined[k]
    ]
    label_w = max(len(c) for c in cols)
    rows = [
        ("agreement_rate", "agreement"),
        ("mean_gap", "mean gap"),
        ("sim_delta", "SIM lift (abs)"),
        ("neutral_delta", "NEUTRAL (control)"),
        ("learning_separation", "** SEPARATION **"),
        ("re_leak", "RE within-dom leak"),
        ("swe_sim", "SWE SIM lift"),
    ]
    header = " " * 20 + "".join(f"{c:>{label_w + 2}}" for c in cols)
    print(header)
    for key, name in rows:
        line = f"{name:<20}"
        for c in cols:
            v = combined[c].get(key)
            if isinstance(v, dict):  # pooled msd block
                v = v.get("mean")
            line += f"{v:>{label_w + 2}}" if v is not None else f"{'-':>{label_w + 2}}"
        print(line)


if __name__ == "__main__":
    main()
