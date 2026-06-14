# Pre-release checklist

Status as of 2026-06-14. Tick the remaining `[ ]` items before making the
repository public.

## Security / secrets
- [x] No API keys, tokens, or credentials in any shipped file. Automated scrub
      (`assemble_artifact_release.py`) scans every text file for known secret
      patterns (OpenAI / Anthropic / AWS / GitHub) and fails the build on a hit.
- [x] No `.env` shipped; `.gitignore` blocks `.env*` and `*.key`.
- [x] Only localhost defaults appear in scripts (env-overridable); the only DB
      string is the public docker-compose dev default
      (`mizaan:mizaan_dev@localhost`), not a real credential.

## Data redistribution
- [x] Third-party GitHub text NOT shipped — references + SHA-256 hashes only.
- [x] `github_raw.json` excluded.
- [x] Commercial RE source NOT shipped — metadata-only manifest; the `.xlsx`
      excluded.
- [x] `results/*.jsonl` confirmed to contain no raw item text (ids + scores +
      telemetry only); `phase_D_decisions.json` carries only the authored
      amendment + approval record.
- [x] **Named entities in `synthetic_re.jsonl` verified clean** (2026-06-14):
      no firm names, emails, phone numbers, or agent/contact names. Only real
      reference is "Jumeirah Golf Estates" — a geographic community used as a
      location (acceptable, like "Palm Jumeirah"). The fabricated firm names
      ("Morin Properties" etc.) are confined to the excluded commercial items.

## Reproducibility / docs
- [x] Tier-1 offline reproduction verified standalone (no backend imports in
      `eval_aggregate.py` / `eval_offline.py` / `eval_figures.py`).
- [x] Model versions, dependencies, and approximate cost/time documented
      (`README.md`, `REPRODUCIBILITY.md`).
- [x] Maintenance expectations stated (research artifact, unmaintained).
- [ ] **Run Tier-1 end-to-end on a fresh environment** (clean venv:
      `pip install -r requirements.txt` then the three offline scripts) and
      confirm `aggregate.json` / `offline_analyses.json` / figures regenerate.
- [ ] **Run Tier-2 smoke test** (optional, needs the Mizaan backend + an LLM
      key): one phase-A run reproduces ~88% cold agreement.

## Licensing
- [x] `LICENSE` = Apache-2.0 (verbatim from apache.org), for code.
- [x] `DATA_LICENSE` = CC-BY-4.0, scoped to authored data.

## Wiring to the paper
- [x] **Repo URL recorded:** <https://github.com/JawedCIA/mizaan-eval>
      (README header). Repo still needs to be created + pushed.
- [x] **Data/Code Availability statement added** to the paper (main.tex),
      pointing to the repo URL.
- [x] **Contact emails confirmed** in the paper: `m.jawed@mannatai.com`,
      `mdjawed2025@iitkalumni.org`.
- [ ] **Push this staging tree** to the GitHub repo (contents become repo root).
      Ensure the repo is live (at least README) when the paper is posted.
- [ ] Replace `TODO-arxiv-id` / `TODO-link` (arXiv id + PDF) once known.
- [ ] `TODO-mizaan-repo-link` (the Mizaan backend, needed for Tier-2): decide
      whether the backend is published; if not, Tier-2 is reproducible only by
      the author / on request (Tier-1 is unaffected).
- [ ] Confirm the release window: ready within 1–2 weeks of the arXiv posting
      (does not need to precede submission).
