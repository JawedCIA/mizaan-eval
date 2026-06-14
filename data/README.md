# Datasets

The evaluation uses 108 work items across two domains (software-engineering
work items, real-estate listings), split into CORRECT (25), HOLDOUT_SIM (25),
and NEUTRAL (58). See `../EVAL_PROTOCOL.md` for the full design.

## What ships here

| File | Items | Text? | License |
|---|---|---|---|
| `synthetic_swe.jsonl` | authored SWE CORRECT + HOLDOUT_SIM | yes | CC-BY-4.0 |
| `synthetic_re.jsonl` | authored RE CORRECT + HOLDOUT_SIM + synthetic NEUTRAL | yes | CC-BY-4.0 |
| `swe_neutral_manifest.jsonl` | 38 GitHub-issue NEUTRAL | **no** (refs + hash) | refs only |
| `re_commercial_manifest.jsonl` | 10 commercial-source NEUTRAL | **no** (metadata) | not redistributed |

The full runner manifests (`swe.jsonl`, `re.jsonl`) and the raw caches
(`github_raw.json`, the commercial `.xlsx`) are **intentionally excluded**
because they embed third-party / commercial text.

## Manifest schemas

`swe_neutral_manifest.jsonl` (one JSON object per line):

```json
{"id": "swe-gh-001", "domain": "swe",
 "source": "github:microsoft/vscode#191229",
 "quality_band": "unknown", "split": "NEUTRAL", "paired_with": null,
 "text_sha256": "<sha256 of the original issue text>"}
```

`re_commercial_manifest.jsonl`:

```json
{"id": "re-xlsx-1", "domain": "re", "source": "commercial:not_redistributed",
 "quality_band": "high", "split": "NEUTRAL", "paired_with": null}
```

## Reconstructing the NEUTRAL splits (Tier-2 only)

The offline reproduction (Tier 1) needs **none** of this — paper numbers come
from `../results/`. You only need item text to re-run scoring end to end.

- **SWE NEUTRAL:** re-fetchable from the public GitHub API.
  `python ../scripts/eval_prepare_datasets.py` pulls each referenced issue and
  rebuilds the full `swe.jsonl`. Compare each item's `text_sha256` against this
  manifest to detect drift (issues may have been edited or deleted since the
  original pull).
- **RE NEUTRAL:** derived from a commercial listings export that is **not**
  redistributable. These 10 items cannot be reconstructed from this release;
  the manifest documents their ids/splits so the experimental structure is
  fully specified. Substitute your own comparable listings to approximate the
  RE NEUTRAL condition.
