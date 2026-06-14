# Mizaan Evaluation Protocol (pre-registered)

**Status:** DESIGN FROZEN before any result is observed. Changes after the
first full run must be logged in the Amendments section at the bottom, with
reasons — this is what lets the paper say the protocol was pre-registered.

**Paper claims under test**
- **C1** Inter-agent disagreement separates reliable from unreliable scores.
- **C2** Counterfactual attribution distinguishes learning-induced
  disagreement from error.
- **C3** The policy channel (promotion) transfers lessons to BOTH agents and
  reduces exemplar dependence.
- **C4** The canary detects injected bad lessons.

---

## 1. Datasets (target N = 100–200 total)

### Domain 1 — Software engineering work items (target 60–100)
| Source | Count | Notes |
|---|---|---|
| Public GitHub issues (closed, descriptive) | 40–60 | repos: large OSS projects; strip usernames/emails; keep title+body |
| Synthetic user stories (LLM-generated, then human-skimmed) | 20–40 | mixed quality on purpose: complete / vague / missing-criteria |

**Rubric `swe-workitem-v1`** (4 dims): Problem clarity (0.3), Reproducibility
or acceptance criteria (0.3), Impact articulation (0.25), Scope realism (0.15).

### Domain 2 — Real-estate listings (target 40–80)
| Source | Count | Notes |
|---|---|---|
| `Refrences/Dataset/dubai_luxury_listings.xlsx` | as available | public listings already collected |
| Public Bayut/PF listings (copy text only) | to fill | mix high/medium/low quality |
| Synthetic listings (LLM-generated, human-skimmed) | 15–25 | deliberately varied quality |

**Rubric `re-listing-v1`** (4 dims): Completeness (0.3), Appeal/writing
quality (0.25), Target-audience fit (0.25), Credibility — no inflated claims
(0.2).

**Dataset manifest**: every item gets `{id, domain, source, text, quality_band
(author's a-priori High/Med/Low tag where known)}` in
`eval/datasets/{swe,re}.jsonl`. The manifest is committed BEFORE scoring.

### Holdout structure (the key design)
Within each domain, items are partitioned BEFORE the run:
- **CORRECT set (~25%)** — items the scripted reviewer will override.
- **HOLDOUT-SIM (~25%)** — items deliberately similar in *pattern* to CORRECT
  items (same lesson applies). Used to measure learning transfer. Similarity
  is by design/construction (paired authoring), not by post-hoc cosine.
- **NEUTRAL (~50%)** — items the lessons should NOT apply to. Used to measure
  over-generalization (false learning).

Each HOLDOUT-SIM item records `paired_with: <correct-item-id>` in the manifest.

## 2. Pre-registered override rules (the "scripted reviewer")

Written here BEFORE the run; the reviewer script applies them mechanically.

**Rule S1 (software):** Items that clearly identify the affected user
population and business impact but lack polish are UNDER-scored by LLMs →
override to 8.5–9.0 with rationale "reward impact articulation over polish".
Applies to tagged CORRECT items in domain 1.

**Rule R1 (real estate):** Listings that disclose limitations honestly
(e.g., notes facing, age, service fees) read as "weaker" to LLMs →
override to 8.5 with rationale "reward credibility and honest disclosure".
Applies to tagged CORRECT items in domain 2.

**Rule X1 (BAD lesson — canary test only, separate phase):** Override a small
set to 9.5 with rationale "long listings deserve top scores" (deliberately
wrong). Used ONLY in Phase E; its data is excluded from C1–C3 analysis.

**Expected-direction ground truth for C2:** a warm-vs-auditor gap counts as
"learning" iff the item is HOLDOUT-SIM paired to a corrected item AND the
learning delta moves toward the override score; otherwise "error".

## 3. Run matrix

| Phase | What happens | Measures |
|---|---|---|
| **A. Cold baseline** | Score ALL items, empty feedback store | δ distribution, path shares, per-item warm==cold sanity |
| **B. Corrections** | Apply Rules S1/R1 to CORRECT set via /feedback | — |
| **C. Instance learning** | Re-score HOLDOUT-SIM + NEUTRAL | learning deltas (SIM↑ expected, NEUTRAL≈0), attribution confusion matrix, path shares |
| **D. Promotion** | Run detect; human (the author) approves faithful drafts, rejects others — decisions logged verbatim | drafted text, approve/reject log |
| **E. Post-promotion** | Re-score HOLDOUT-SIM + NEUTRAL | cold & auditor movement (C3), exemplars retrieved (expect 0 for promoted), path shares |
| **F. Canary** | Apply Rule X1, let learned-accepts flow, spot-checks reviewed honestly | overturn rate rise, detection latency |

**Repetitions:** the full matrix runs **r=3** times minimum (r=5 if budget
allows) with fresh DBs. LLM nondeterminism is the "seed"; report mean ± sd
(or median/IQR) for every aggregate. Telemetry endpoint
(`/api/v1/analytics/telemetry`) is captured after every phase.

## 4. Configuration (frozen)

```
DEFAULT_LLM_MODEL=gpt-4o-mini          # report exact snapshot from API response
EMBEDDING_DIM=1536                      # text-embedding-3-small
RETRIEVAL_SIMILARITY_THRESHOLD=0.55
CLUSTER_SIMILARITY_THRESHOLD=0.55
AGREEMENT_THRESHOLD=1.0
COLD_AGREEMENT_THRESHOLD=0.75
SPOT_CHECK_RATE=0.1
PROMOTION_MIN_CLUSTER=3
```
Any change → log in Amendments.

## 5. Metrics & reporting (what goes in the paper)

1. **δ distribution** per domain & phase (violin/hist + % ≤ 1.0).
2. **Path shares** per phase (AUTO_ACCEPT / AUTO_ACCEPT_LEARNED /
   HUMAN_REQUIRED) — phase C vs A shows the false-escalation problem being
   absorbed by AUTO_ACCEPT_LEARNED; baseline "warm-gap-only router" computed
   offline from the same scores (re-route stored triples with cold ignored).
3. **Learning delta** distributions: HOLDOUT-SIM vs NEUTRAL (the gap between
   them is the real learning signal; NEUTRAL ≠ 0 indicates leakage).
4. **Attribution confusion matrix** (C2): router verdict vs ground truth.
5. **Three-era trajectories** (C3): cold/warm/auditor means on HOLDOUT-SIM
   across phases A→C→E; exemplar counts before/after retirement.
6. **Canary** (C4): overturn-rate time series in phase F; cases-to-detection.
7. **Cost**: generations + tokens per item per phase (from persisted
   tool-call records).

**Statistics:** report distributions, not just means; paired comparisons on
the same items across phases (Wilcoxon signed-rank for deltas); no p-hacking
— the tests named here are the tests reported.

## 6. Artifacts (released with the paper)

- `eval/datasets/*.jsonl` (manifest + items, post-anonymization)
- `eval/rules.json` (pre-registered override rules)
- `eval/results/run_<r>/phase_<X>.json` (raw per-item records)
- `eval/results/summary.json` (aggregates the paper cites)
- `mizaan/scripts/eval_runner.py` (this protocol, executable)
- Approve/reject log for amendments (verbatim)

**Paper rule:** every number in Section 6 must be traceable to
`eval/results/summary.json`. No exceptions.

## 7. Honesty constraints

- The "Expected Results" tables in `04_evaluation_plan.md` are PREDICTIONS;
  they never appear in the paper as results.
- The old draft's fabricated numbers (87% agreement, 23% gains, testimonials)
  are dead. Never reuse.
- If results are unflattering (e.g., attribution accuracy mediocre), they are
  reported as-is; the paper's contribution is the mechanism + honest
  measurement, not a benchmark win.

---

## Amendments log

- **2026-06-13 — scoring parallelized from run 2 (run 1 was sequential).**
  `eval_runner.py` `phase_score` now scores items with bounded concurrency
  (`EVAL_WORKERS=5` default) using a thread pool over the same `httpx.Client`.
  Reason: each run's wall-clock was ~2.5–3 h sequential; concurrency brings it
  to ~45 min. **No effect on results:** scoring only READS the feedback store
  (overrides are written only in phase B, promotion only in phase D), so item
  order within a scoring phase is irrelevant. Phases B/D/F-inject remain
  sequential (they write feedback). Model, thresholds, datasets, splits, and
  override rules are unchanged. Run 1 records remain valid and comparable.

- **2026-06-13 — model-generalization extension (run 4).** A single
  supplementary run on a contrasting generation model (\texttt{gpt-4.1};
  embeddings unchanged at \texttt{text-embedding-3-small}), \textbf{phases
  A--C only} (cold baseline, overrides, instance learning), reported as a
  generalization check, NOT primary results. Purpose: neutralize the
  single-model reviewer concern by testing whether the qualitative patterns
  (SIM\,$>$\,NEUTRAL learning, within-domain leakage, cold agreement)
  replicate; absolute numbers are not expected to match runs 1--3.
  Implementation notes: gpt-4.1 has a 30k TPM limit on this account, so this
  run uses `EVAL_WORKERS=2` and the runner now retries transient
  rate-limit/5xx responses with exponential backoff (`_post_retrying`). The
  retry path is a pure robustness fix; it does not alter any scored result.
