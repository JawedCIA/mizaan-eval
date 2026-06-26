# Reproducibility manifest — "When Disagreement Means Learning"

Maps every paper figure and headline number to the exact script, input, and
output that produced it. Paths are relative to this repository root.

Frozen eval model for the main result: **gpt-4o-mini** +
`text-embedding-3-small` (1536-dim). Robustness passes: **gpt-4.1** and
**claude-sonnet-4-6** (phases A–C only).

> Every number in the paper's Section 6 traces to a JSON file under `results/`.
> Those files contain only item ids, scores, and telemetry — no raw item text —
> so the paper's claims are reproducible even though two data splits are not
> redistributed (see `data/README.md`).

## Two tiers

- **Tier 1 (offline, no backend):** `results/*` → analysis scripts → numbers +
  figures. Pure Python; this is what verifies the paper.
- **Tier 2 (full re-run):** `data/*` → `eval_runner.py` against a live Mizaan
  API → `results/*`. Needs the backend, an LLM key, and reconstructed data.

## Pipeline

```
data/*.jsonl ──> scripts/eval_runner.py ──> results/run_{1,2,3}/phase_{A..F}.jsonl
   (Tier 2)              │                          │
                         │ (gpt-4.1 / sonnet,       ├─> scripts/eval_aggregate.py ─> results/aggregate.json
                         │  A–C, runs 4/5)          ├─> scripts/eval_offline.py   ─> results/offline_analyses.json
                         └─> results/run_{4,5}/*    └─> scripts/eval_generalization.py ─> results/generalization_{gpt41,claude}.json
                                                                  │  (Tier 1)
aggregate.json + offline_analyses.json ──> scripts/eval_figures.py ──> figures/fig5,fig6.pdf
figures/fig{1..4}.tex (hand-authored TikZ) ──> [render in a LaTeX engine]
```

## Scripts (`scripts/`)

| Script | Tier | Role | Reads | Writes |
|---|---|---|---|---|
| `eval_prepare_datasets.py` | 2 | Rebuild dataset manifests (GitHub fetch + xlsx) | refs + sources | `swe.jsonl`, `re.jsonl` (local, not shipped) |
| `eval_runner.py` | 2 | Run phases A–F vs a live API; interactive promotion approval; telemetry | `data/*.jsonl`, live API | `results/run_N/*` |
| `eval_aggregate.py` | 1 | Pool n=3 runs → mean ± sd | `run_{1,2,3}/phase_*.jsonl` | `results/aggregate.json` |
| `eval_offline.py` | 1 | Attribution matrix, τ_c sweep, warm-gap-only baseline reroute | `run_{1,2,3}/phase_*.jsonl` | `results/offline_analyses.json` |
| `eval_generalization.py` | 1 | Roll up gpt-4.1 / sonnet runs vs the n=3 baseline | `run_{1,4,5}/*` | `results/generalization_*.json` |
| `eval_figures.py` | 1 | Render data figures | `aggregate.json`, `offline_analyses.json` | `figures/fig5,fig6.pdf` |

Demo scripts (`demo_*.py`, Tier 2) are single-case proofs, not paper data.

## Figures

| Figure | Source | Type | Produced by |
|---|---|---|---|
| Fig 1–4 (architecture, workflow, decision tree, channels) | `figures/fig{1..4}.tex` | TikZ | hand-authored; render in a LaTeX engine |
| Fig 5 Consolidation | `figures/fig5_consolidation.pdf` | matplotlib | `eval_figures.py` ← `aggregate.json` |
| Fig 6 τ_c sweep | `figures/fig6_tauc_sweep.pdf` | matplotlib | `eval_figures.py` ← `offline_analyses.json` |

## Headline numbers → source

All from `results/aggregate.json` (gpt-4o-mini, pooled n=3) unless noted.

| Paper claim | Value | Source key |
|---|---|---|
| Cold inter-agent agreement | 88.3 ± 0.5% | `agreement_rate` |
| Mean inter-agent gap | 0.705 ± 0.023 | `mean_gap` |
| Instance learning, SIM held-out | +0.326 | `sim_delta` |
| Control (NEUTRAL) | +0.122 | `neutral_delta` |
| **Learning separation (SIM−NEUTRAL)** | **+0.204 ± 0.006** | `learning_separation` |
| Within-domain leakage (RE NEUTRAL) | +0.353 ± 0.025 | `re_leak` |
| Consolidation eras (warm/cold/auditor, exemplars) | per-era triples | aggregate consolidation block |
| Attribution confusion matrix | TP1/FN21/FP5/TN42 | `offline_analyses.json` |
| τ_c sweep (no clean separation) | curve | `offline_analyses.json` |
| Baseline reroute (warm-only 27.7% vs cf@0.75 25.3%) | rates | `offline_analyses.json` |
| Retrieval-hit fraction (cost) | 47% | phase C across runs |

## Generalization (robustness, phases A–C only, no promotion)

From `results/generalization_{gpt41,claude}.json`. The model-robustness claim
rests on the **separation** row, not absolute lifts:

| Metric | gpt-4o-mini (n=3) | gpt-4.1 (run 4) | claude-sonnet-4-6 (run 5) |
|---|---|---|---|
| Learning separation | 0.204 ± 0.006 | 0.211 | 0.310 |
| Agreement | 88.3% | 91.7% | 95.4% |

Separation stays positive across models; absolute lift and within-domain
leakage vary with the base model (see paper §6.7).

## Tier-1 quick start

```bash
pip install -r requirements.txt
python scripts/eval_aggregate.py
python scripts/eval_offline.py
python scripts/eval_figures.py
```

## Tier-2 full re-run (summary)

1. Stand up the Mizaan backend (not publicly released — available from the
   author on request): Postgres + pgvector,
   the API, `.env` with `DEFAULT_LLM_MODEL=gpt-4o-mini`, `EMBEDDING_DIM=1536`,
   `RETRIEVAL_SIMILARITY_THRESHOLD=0.55`, `CLUSTER_SIMILARITY_THRESHOLD=0.55`.
2. Reconstruct datasets (`scripts/eval_prepare_datasets.py`; RE NEUTRAL needs
   your own commercial source — see `data/README.md`).
3. Per run, fresh DB: `eval_runner.py --run N --phase A` … `F` (approve the
   amendment at phase D when prompted).
4. After 3 runs: `eval_aggregate.py`, `eval_offline.py`, `eval_figures.py`.

Frozen-config caveats: run 1 sequential; runs 2–3 used `EVAL_WORKERS=5`; the
gpt-4.1 pass used `EVAL_WORKERS=2` (30k TPM; runner retries 429/500 with
exponential backoff). See `EVAL_PROTOCOL.md` Amendments.
