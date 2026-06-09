"""Offline BIRD dev preparation: unzip the databases and build a pinned subset.

Run once: `uv run python eval/prep_bird.py`. Idempotent. No network, no API.

The subset is a seeded, stratified sample across db_id x difficulty so the eval
covers every database and difficulty band while staying small enough to run on a
budget. eval/bird_subset.json is committed so the run is reproducible.
"""

from __future__ import annotations

import json
import random
import zipfile
from collections import defaultdict
from pathlib import Path

BIRD_DIR = Path(__file__).parent.parent / "data" / "raw" / "bird" / "dev" / "dev_20240627"
DEV_JSON = BIRD_DIR / "dev.json"
DATABASES_ZIP = BIRD_DIR / "dev_databases.zip"
DATABASES_DIR = BIRD_DIR / "dev_databases"
SUBSET_PATH = Path(__file__).parent / "bird_subset.json"

SUBSET_SIZE = 100
SEED = 20260609


def bird_db_path(db_id: str) -> Path:
    """Resolve a db_id to its extracted SQLite file."""
    return DATABASES_DIR / db_id / f"{db_id}.sqlite"


def extract_databases() -> None:
    """Unzip dev_databases.zip if the databases are not already extracted."""
    if DATABASES_DIR.exists() and any(DATABASES_DIR.iterdir()):
        print(f"Databases already extracted at {DATABASES_DIR}")
        return
    if not DATABASES_ZIP.exists():
        raise FileNotFoundError(f"Missing {DATABASES_ZIP}; download the BIRD dev set first.")
    print(f"Extracting {DATABASES_ZIP} ...")
    with zipfile.ZipFile(DATABASES_ZIP) as zf:
        for member in zf.namelist():
            if "__MACOSX" in member or member.endswith(".DS_Store"):
                continue
            zf.extract(member, BIRD_DIR)
    print(f"Extracted to {DATABASES_DIR}")


def _stratified_sample(
    questions: list[dict[str, object]], size: int, seed: int
) -> list[dict[str, object]]:
    """Sample `size` questions stratified by (db_id, difficulty), deterministically."""
    strata: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for q in questions:
        strata[(str(q["db_id"]), str(q["difficulty"]))].append(q)

    total = len(questions)
    rng = random.Random(seed)
    chosen: list[dict[str, object]] = []
    for key in sorted(strata):
        bucket = sorted(strata[key], key=lambda q: int(str(q["question_id"])))
        n = max(1, round(len(bucket) / total * size))
        n = min(n, len(bucket))
        chosen.extend(rng.sample(bucket, n))

    chosen.sort(key=lambda q: int(str(q["question_id"])))
    # Trim deterministically if rounding overshot the target.
    if len(chosen) > size:
        chosen = rng.sample(chosen, size)
        chosen.sort(key=lambda q: int(str(q["question_id"])))
    return chosen


def build_subset() -> None:
    """Build and write the pinned subset from dev.json."""
    questions: list[dict[str, object]] = json.loads(DEV_JSON.read_text(encoding="utf-8"))
    subset = _stratified_sample(questions, SUBSET_SIZE, SEED)

    by_db: dict[str, int] = defaultdict(int)
    by_difficulty: dict[str, int] = defaultdict(int)
    for q in subset:
        by_db[str(q["db_id"])] += 1
        by_difficulty[str(q["difficulty"])] += 1

    payload = {
        "seed": SEED,
        "target_size": SUBSET_SIZE,
        "actual_size": len(subset),
        "source": "BIRD dev (dev_20240627)",
        "by_db": dict(sorted(by_db.items())),
        "by_difficulty": dict(sorted(by_difficulty.items())),
        "questions": subset,
    }
    SUBSET_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(subset)} questions to {SUBSET_PATH}")
    print(f"  by db: {dict(sorted(by_db.items()))}")
    print(f"  by difficulty: {dict(sorted(by_difficulty.items()))}")


def main() -> None:
    extract_databases()
    build_subset()


if __name__ == "__main__":
    main()
