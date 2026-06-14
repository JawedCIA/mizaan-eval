"""Build the evaluation dataset manifests (EVAL_PROTOCOL.md section 1).

Sources:
  1. GitHub closed issues (public API, no auth)  -> SWE NEUTRAL items
  2. Refrences/Dataset/dubai_luxury_listings.xlsx -> RE NEUTRAL items
  3. Hand-authored synthetic files (checked in):
       eval/datasets/synthetic_swe.jsonl  (CORRECT + HOLDOUT_SIM pairs)
       eval/datasets/synthetic_re.jsonl   (CORRECT + HOLDOUT_SIM pairs + NEUTRAL)

Output (the frozen manifests the runner consumes):
       eval/datasets/swe.jsonl
       eval/datasets/re.jsonl

Re-running is deterministic for sources 2-3; source 1 caches its raw pull in
eval/datasets/github_raw.json so the manifest never silently changes after
the first pull. Delete the cache to re-pull.

Usage:
    python scripts/eval_prepare_datasets.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "Refrences/DocBase/PublishPaper/eval"
DATASET_DIR = EVAL_DIR / "datasets"
XLSX = REPO_ROOT / "Refrences/Dataset/dubai_luxury_listings.xlsx"
GITHUB_CACHE = DATASET_DIR / "github_raw.json"

# Repos chosen for descriptive, well-triaged closed issues.
GITHUB_REPOS = [
    ("microsoft", "vscode"),
    ("facebook", "react"),
    ("django", "django"),
    ("pallets", "flask"),
    ("microsoft", "TypeScript"),
    ("nodejs", "node"),
    ("pandas-dev", "pandas"),
    ("fastapi", "fastapi"),
]
PER_REPO = 18  # pull extra; filtered down to TARGET_GITHUB
TARGET_GITHUB = 40
MIN_BODY_CHARS = 200
MAX_BODY_CHARS = 3500


def _clean(text: str) -> str:
    """Strip markdown noise, image refs, HTML comments, and usernames."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " [image] ", text)  # images
    text = re.sub(r"```[a-zA-Z]*\n", "\n", text).replace("```", "\n")
    text = re.sub(r"@[A-Za-z0-9_-]{2,}", "[user]", text)  # usernames
    text = re.sub(r"https?://\S+", "[link]", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pull_github() -> list[dict]:
    if GITHUB_CACHE.exists():
        print(f"using cached GitHub pull: {GITHUB_CACHE}")
        return json.loads(GITHUB_CACHE.read_text(encoding="utf-8"))

    raw: list[dict] = []
    with httpx.Client(
        headers={"Accept": "application/vnd.github+json"},
        follow_redirects=True,
    ) as client:
        for owner, repo in GITHUB_REPOS:
            r = client.get(
                f"https://api.github.com/repos/{owner}/{repo}/issues",
                params={"state": "closed", "per_page": PER_REPO,
                        "sort": "comments", "direction": "desc"},
                timeout=30,
            )
            r.raise_for_status()
            for issue in r.json():
                if "pull_request" in issue:
                    continue
                body = issue.get("body") or ""
                if not (MIN_BODY_CHARS <= len(body) <= MAX_BODY_CHARS):
                    continue
                raw.append({
                    "repo": f"{owner}/{repo}",
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": body,
                    "labels": [label["name"] for label in issue.get("labels", [])],
                })
            print(f"  {owner}/{repo}: {len(raw)} usable so far")
    GITHUB_CACHE.parent.mkdir(parents=True, exist_ok=True)
    GITHUB_CACHE.write_text(json.dumps(raw, indent=1), encoding="utf-8")
    return raw


def github_items() -> list[dict]:
    raw = pull_github()[:TARGET_GITHUB]
    items = []
    for i, issue in enumerate(raw, 1):
        text = f"{issue['title']}\n\n{_clean(issue['body'])}"
        items.append({
            "id": f"swe-gh-{i:03d}",
            "domain": "swe",
            "source": f"github:{issue['repo']}#{issue['number']}",
            "text": text[:MAX_BODY_CHARS],
            "quality_band": "unknown",
            "split": "NEUTRAL",
            "paired_with": None,
        })
    return items


def xlsx_items() -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(XLSX, read_only=True)
    ws = wb["Property Listings"]
    rows = list(ws.iter_rows(values_only=True))
    header_idx = next(i for i, r in enumerate(rows) if r[0] == "ID")
    header = [str(h) for h in rows[header_idx]]
    items = []
    for r in rows[header_idx + 1:]:
        if not r[0]:
            continue
        rec = dict(zip(header, r, strict=False))
        quality = str(rec.get("Quality", "")).strip().lower()
        text = (
            f"{rec.get('Listing Title', '')}\n\n"
            f"{rec.get('Description', '')}\n\n"
            f"Property type: {rec.get('Property Type', '')} | "
            f"Location: {rec.get('Location', '')} | "
            f"Price: AED {rec.get('Price (AED)', '')} | "
            f"Size: {rec.get('Size (sq ft)', '')} sq ft | "
            f"Bedrooms: {rec.get('Bedrooms', '')} | "
            f"Bathrooms: {rec.get('Bathrooms', '')}\n"
            f"Developer/Community: {rec.get('Developer / Community', '')}\n"
            f"Key features: {rec.get('Key Features', '')}\n"
            f"Investment highlights: {rec.get('Investment Highlights', '')}\n"
            f"Payment plan: {rec.get('Payment Plan', '')}"
        )
        items.append({
            "id": f"re-xlsx-{str(rec.get('ID', '')).strip()}",
            "domain": "re",
            "source": "dataset:dubai_luxury_listings.xlsx",
            "text": text.strip(),
            "quality_band": quality if quality in ("high", "med", "low") else "unknown",
            "split": "NEUTRAL",
            "paired_with": None,
        })
    return items


def synthetic_items(name: str) -> list[dict]:
    path = DATASET_DIR / f"synthetic_{name}.jsonl"
    if not path.exists():
        print(f"!! missing {path} — author the synthetic items first")
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def validate(items: list[dict], domain: str) -> None:
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)), f"duplicate ids in {domain}"
    by_id = {i["id"]: i for i in items}
    for item in items:
        assert item["domain"] == domain
        assert item["split"] in ("CORRECT", "HOLDOUT_SIM", "NEUTRAL")
        if item["split"] == "HOLDOUT_SIM":
            assert item.get("paired_with") in by_id, \
                f"{item['id']} paired_with missing: {item.get('paired_with')}"
            assert by_id[item["paired_with"]]["split"] == "CORRECT"
    splits = {s: sum(1 for i in items if i["split"] == s)
              for s in ("CORRECT", "HOLDOUT_SIM", "NEUTRAL")}
    print(f"  {domain}: {len(items)} items, splits {splits}")


def write_manifest(items: list[dict], name: str) -> None:
    path = DATASET_DIR / f"{name}.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"  wrote {path}")


def main() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    print("[1] SWE: GitHub issues (NEUTRAL)")
    swe = github_items()
    print("[2] SWE: synthetic CORRECT/HOLDOUT_SIM pairs")
    swe += synthetic_items("swe")
    validate(swe, "swe")
    write_manifest(swe, "swe")

    print("[3] RE: xlsx listings (NEUTRAL)")
    re_items = xlsx_items()
    print("[4] RE: synthetic items")
    re_items += synthetic_items("re")
    validate(re_items, "re")
    write_manifest(re_items, "re")

    print("\nDone. Review eval/datasets/*.jsonl, then freeze (commit) before any run.")


if __name__ == "__main__":
    main()
