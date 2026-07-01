"""entity_resolver.py — patient identity resolution across silos.

Adapted directly from GhostTrace's entity_resolver.py (built for corporate
ownership chain deduplication). The core technique is identical: normalize,
then score similarity by the max of a direct ratio, a token-sort ratio, and
a token-set ratio, so word order and minor spelling drift don't defeat a
match. What's added here is a second, independent signal that GhostTrace's
domain didn't have: date of birth. A shell company has no DOB equivalent;
a patient does, and it is a much stronger identity signal than name
similarity alone. Two patients can share a common name; two patients
essentially never share a name AND a date of birth.

Three bands (thresholds in config), gated by DOB:
  name similarity >= FUZZY_AUTO_MERGE_THRESHOLD AND DOB exact match
      -> merge automatically
  name similarity >= FUZZY_ADJUDICATE_THRESHOLD AND DOB exact or near match
      -> ask the adjudicator
  otherwise -> distinct patients

No web, no database, no Claude import. The adjudicator is injected as a
plain callable so this module tests without mocking anything but a
function -- same design as GhostTrace.
"""
from __future__ import annotations

from datetime import date
from difflib import SequenceMatcher
from typing import Callable

from config import (
    DOB_NEAR_MATCH_DAYS,
    FUZZY_ADJUDICATE_THRESHOLD,
    FUZZY_AUTO_MERGE_THRESHOLD,
)

# Adjudicator signature: (record_a, record_b) -> bool (same patient?)
Adjudicator = Callable[[dict, dict], bool]


def normalize_name(first: str, last: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    raw = f"{first or ''} {last or ''}"
    cleaned = "".join(ch if ch.isalnum() or ch == " " else " " for ch in raw.lower())
    return " ".join(cleaned.split())


def name_similarity(a: dict, b: dict) -> float:
    """0-100 similarity between two patients' names.

    Takes the max of three measures so word order and single-token typos
    don't defeat the match:
      - direct: SequenceMatcher on "first last"
      - token-sort: same, after sorting tokens (catches "Last, First" style
        capture in one silo vs "First Last" in another)
      - token-set: Jaccard overlap of token sets
    """
    na = normalize_name(a.get("first_name", ""), a.get("last_name", ""))
    nb = normalize_name(b.get("first_name", ""), b.get("last_name", ""))
    if not na or not nb:
        return 0.0
    if na == nb:
        return 100.0
    direct = SequenceMatcher(None, na, nb).ratio()
    ta, tb = na.split(), nb.split()
    token_sort = SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    sa, sb = set(ta), set(tb)
    token_set = len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0
    return max(direct, token_sort, token_set) * 100


def parse_dob(raw: str) -> date | None:
    """Accepts ISO (YYYY-MM-DD), US slash (M/D/YYYY or MM/DD/YYYY) formats
    -- the exact formats used across PatientFusion's four silos."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        if "-" in raw:
            y, m, d = raw.split("-")
            return date(int(y), int(m), int(d))
        if "/" in raw:
            m, d, y = raw.split("/")
            return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None
    return None


def dob_match(a: dict, b: dict) -> str:
    """Returns 'exact', 'near', or 'none'."""
    da, db = parse_dob(a.get("dob", "")), parse_dob(b.get("dob", ""))
    if da is None or db is None:
        return "none"
    if da == db:
        return "exact"
    if abs((da - db).days) <= DOB_NEAR_MATCH_DAYS:
        return "near"
    # Classic day/month transposition slip: same year, day and month swapped
    if da.year == db.year and da.day == db.month and da.month == db.day:
        return "near"
    return "none"


def resolve_patients(
    raw_records: list[dict],
    adjudicator: Adjudicator | None = None,
) -> tuple[list[dict], dict[int, int]]:
    """Collapse per-silo patient records into canonical master patients.

    raw_records: list of dicts, each with at least first_name, last_name,
    dob, gender, and a 'silo' + '_index' key identifying its origin (added
    by the caller so results can be traced back to source rows).

    Returns (master_patients, record_index_to_master_index) where the
    second value maps each raw_records list position to the master
    patient it was assigned to.

    With no adjudicator, the ambiguous band stays unmerged: a missed merge
    means a patient's timeline is split across two entries (recoverable by
    reviewing the population list); a wrong merge blends two real
    patients' medical histories together (not recoverable, and the more
    dangerous failure mode in this domain).
    """
    masters: list[dict] = []
    assignment: dict[int, int] = {}
    verdict_cache: dict[frozenset, bool] = {}

    def _ask(a: dict, b: dict) -> bool:
        if adjudicator is None:
            return False
        key = frozenset((id(a), id(b)))
        if key not in verdict_cache:
            verdict_cache[key] = adjudicator(a, b)
        return verdict_cache[key]

    for idx, raw in enumerate(raw_records):
        best_i = None
        best_score = 0.0
        best_dob = "none"
        for i, master in enumerate(masters):
            score = name_similarity(raw, master)
            if score > best_score:
                best_score = score
                best_i = i
                best_dob = dob_match(raw, master)

        merged = False
        if best_i is not None:
            if best_score >= FUZZY_AUTO_MERGE_THRESHOLD and best_dob == "exact":
                merged = True
            elif best_score >= FUZZY_ADJUDICATE_THRESHOLD and best_dob in ("exact", "near"):
                merged = _ask(raw, masters[best_i])

        if merged:
            master = masters[best_i]
            master["silo_records"].append({"silo": raw["silo"], "index": raw["_index"]})
            # Fill demographic gaps but never overwrite a known value
            for field in ("gender", "first_name", "last_name", "dob"):
                if not master.get(field) and raw.get(field):
                    master[field] = raw[field]
            assignment[idx] = best_i
        else:
            new_master = {
                "first_name": raw.get("first_name", ""),
                "last_name": raw.get("last_name", ""),
                "dob": raw.get("dob", ""),
                "gender": raw.get("gender", ""),
                "silo_records": [{"silo": raw["silo"], "index": raw["_index"]}],
            }
            masters.append(new_master)
            assignment[idx] = len(masters) - 1

    return masters, assignment
