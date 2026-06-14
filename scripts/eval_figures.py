"""Generate the paper's data figures from committed eval JSON (no API).

Outputs vector PDFs into the paper's figures/ dir:
  fig5_consolidation.pdf  — three-era consolidation + leakage elimination
  fig6_tauc_sweep.pdf     — tau_c sensitivity (no clean separation)

Every value is read from aggregate.json / offline_analyses.json, so the
figures are traceable to the same source as Section 6.

Usage:
    python scripts/eval_figures.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _resolve_dirs() -> tuple[Path, Path]:
    """Locate results/ and figures/ in both the source repo and the standalone
    artifact release (where results/ and figures/ are siblings of scripts/)."""
    here = Path(__file__).resolve()
    env = os.environ.get("MIZAAN_RESULTS")
    results = Path(env) if env else here.parent.parent / "results"
    figdir = here.parent.parent / "figures"
    if env or (results / "run_1").exists() or (results / "aggregate.json").exists():
        if figdir.exists():
            return results, figdir
        return (
            results,
            here.parents[2] / "Refrences/DocBase/PublishPaper/mizaan-paper/figures",
        )
    return (
        here.parents[2] / "Refrences/DocBase/PublishPaper/eval/results",
        here.parents[2] / "Refrences/DocBase/PublishPaper/mizaan-paper/figures",
    )


RESULTS, FIGDIR = _resolve_dirs()

# Academic palette (matches the TikZ mz* colors).
BLUE = "#2563EB"
AMBER = "#F59E0B"
TEAL = "#0D9488"
SLATE = "#475569"
PURPLE = "#7C3AED"
INK = "#1E293B"

plt.rcParams.update(
    {
        "font.size": 11,
        "axes.edgecolor": INK,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 150,
    }
)


def load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def fig_consolidation() -> None:
    agg = load("aggregate.json")
    e = agg["consolidation_re_sim"]
    lk = agg["leakage_re_neutral_warm"]
    eras = ["Pre-learning", "Instance", "Post-promotion"]
    x = [0, 1, 2]

    def series(key: str) -> tuple[list[float], list[float]]:
        m = [
            e[era][key]["mean"]
            for era in ("pre_learning", "instance", "post_promotion")
        ]
        s = [
            e[era][key]["sd"] for era in ("pre_learning", "instance", "post_promotion")
        ]
        return m, s

    warm_m, warm_s = series("warm")
    cold_m, cold_s = series("cold")
    aud_m, aud_s = series("auditor")
    ex_counts = [
        e["pre_learning"]["exemplars"][0],
        e["instance"]["exemplars"][0],
        e["post_promotion"]["exemplars"][0],
    ]
    leak_m = [lk["pre"]["mean"], lk["instance"]["mean"], lk["post_promotion"]["mean"]]
    leak_s = [lk["pre"]["sd"], lk["instance"]["sd"], lk["post_promotion"]["sd"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.6))

    # Panel (a): HOLDOUT_SIM warm/cold/auditor
    ax1.errorbar(
        x,
        warm_m,
        yerr=warm_s,
        marker="o",
        color=BLUE,
        lw=2,
        capsize=3,
        label="Primary (warm)",
    )
    ax1.errorbar(
        x,
        cold_m,
        yerr=cold_s,
        marker="s",
        color=BLUE,
        lw=2,
        ls="--",
        capsize=3,
        label="Primary (cold)",
        alpha=0.7,
    )
    ax1.errorbar(
        x, aud_m, yerr=aud_s, marker="^", color=AMBER, lw=2, capsize=3, label="Auditor"
    )
    for xi, c in zip(x, ex_counts, strict=True):
        ax1.annotate(f"{c} exemplars", (xi, 8.07), ha="center", fontsize=8, color=TEAL)
    ax1.set_xticks(x)
    ax1.set_xticklabels(eras, fontsize=9)
    ax1.set_ylabel("Score")
    ax1.set_ylim(8.0, 8.62)
    ax1.set_title("(a) Real-estate Holdout-Sim", fontsize=10)
    ax1.legend(fontsize=8, loc="upper left", frameon=False)
    ax1.annotate(
        "warm$=$cold\nrestored",
        (2, 8.39),
        (1.18, 8.47),
        fontsize=8,
        color=SLATE,
        ha="center",
        arrowprops={"arrowstyle": "->", "color": SLATE},
    )

    # Panel (b): NEUTRAL leakage + elimination
    ax2.errorbar(x, leak_m, yerr=leak_s, marker="o", color=PURPLE, lw=2, capsize=3)
    ax2.axhline(leak_m[0], color=SLATE, lw=1, ls=":", alpha=0.7)
    ax2.annotate("baseline", (0.02, leak_m[0] + 0.01), fontsize=8, color=SLATE)
    ax2.annotate(
        "instance\nleak",
        (1, leak_m[1]),
        (1.1, leak_m[1] - 0.12),
        fontsize=8,
        color=PURPLE,
        arrowprops={"arrowstyle": "->", "color": PURPLE},
    )
    ax2.annotate(
        "eliminated by\npromotion",
        (2, leak_m[2]),
        (1.15, leak_m[2] + 0.08),
        fontsize=8,
        color=PURPLE,
        arrowprops={"arrowstyle": "->", "color": PURPLE},
    )
    ax2.set_xticks(x)
    ax2.set_xticklabels(eras, fontsize=9)
    ax2.set_ylabel("Primary (warm) score")
    ax2.set_title("(b) Real-estate Neutral (control)", fontsize=10)

    fig.tight_layout()
    out = FIGDIR / "fig5_consolidation.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def fig_tauc() -> None:
    off = load("offline_analyses.json")
    sweep = off["tau_c_sweep"]["sweep"]
    tc = [r["tau_c"] for r in sweep if r["tau_c"] <= 1.75]
    recall = [r["learning_recall"] for r in sweep if r["tau_c"] <= 1.75]
    false_attr = [r["false_attribution"] for r in sweep if r["tau_c"] <= 1.75]

    fig, ax = plt.subplots(figsize=(5.0, 3.6))
    ax.plot(tc, recall, marker="o", color=BLUE, lw=2, label="Learning recall")
    ax.plot(tc, false_attr, marker="s", color=AMBER, lw=2, label="False attribution")
    ax.axvline(0.75, color=SLATE, lw=1, ls="--")
    ax.annotate(
        "configured\n$\\tau_c=0.75$",
        (0.75, 0.85),
        (0.85, 0.78),
        fontsize=8,
        color=SLATE,
    )
    ax.set_xlabel("$\\tau_c$ (cold-agreement threshold)")
    ax.set_ylabel("Rate (gapped cases)")
    ax.set_ylim(-0.03, 1.05)
    ax.set_title("$\\tau_c$ sensitivity: no clean separation", fontsize=10)
    ax.legend(fontsize=9, loc="center right", frameon=False)
    fig.tight_layout()
    out = FIGDIR / "fig6_tauc_sweep.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def main() -> None:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig_consolidation()
    fig_tauc()


if __name__ == "__main__":
    main()
