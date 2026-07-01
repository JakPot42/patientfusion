"""nlsearch.py — natural-language population search.

Claude only converts free text into a structured filter; it never decides
which patients match ("Claude extracts, rules decide" -- the doctrine used
throughout this portfolio). execute_filter() is the only thing that
touches patient data, and it is plain deterministic Python.

DEMO_MODE (default) uses a small deterministic keyword parser instead of
calling the Anthropic API, so `patientfusion search "..."` works with zero
API keys, exactly like every other project in this portfolio.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

from config import (
    CLAUDE_MODEL,
    DEFAULT_LOOKBACK_DAYS,
    DEMO_MODE,
    LAB_TEST_MAP,
    MONITORING_REQUIREMENTS,
)
from models import MasterPatient
from screenings import most_recent_lab_date

_KNOWN_DRUGS = sorted({req["drug"] for req in MONITORING_REQUIREMENTS} | {
    "warfarin", "metformin", "lisinopril", "losartan", "digoxin", "verapamil",
    "simvastatin", "amlodipine", "insulin", "hydrochlorothiazide",
})

# Ordered longest-phrase-first so "lipid panel" matches before "panel" etc.
_LAB_SYNONYMS = [
    ("hemoglobin a1c", "a1c"), ("lipid panel", "total_cholesterol"),
    ("kidney function", "egfr"), ("renal function", "egfr"),
    ("cholesterol", "total_cholesterol"), ("triglycerides", "triglycerides"),
    ("creatinine", "creatinine"), ("potassium", "potassium"),
    ("inr", "inr"), ("a1c", "a1c"), ("egfr", "egfr"),
    ("ldl", "ldl"), ("hdl", "hdl"),
]


@dataclass
class SearchFilter:
    drug: str | None = None
    missing_lab_test: str | None = None
    gender: str | None = None

    def to_dict(self) -> dict:
        return {"drug": self.drug, "missing_lab_test": self.missing_lab_test, "gender": self.gender}


def _demo_parse(query: str) -> SearchFilter:
    q = query.lower()
    drug = next((d for d in _KNOWN_DRUGS if d in q), None)
    lab = None
    if any(trigger in q for trigger in ("without", "no recent", "missing", "overdue")):
        for phrase, key in _LAB_SYNONYMS:
            if phrase in q:
                lab = key
                break
    gender = None
    if re.search(r"\b(women|female)\b", q):
        gender = "F"
    elif re.search(r"\b(men|male)\b", q):
        gender = "M"
    return SearchFilter(drug=drug, missing_lab_test=lab, gender=gender)


_CLAUDE_SYSTEM_PROMPT = (
    "Convert the user's natural-language patient search into strict JSON "
    "with exactly these keys: drug (a lowercase generic drug name string, "
    "or null), missing_lab_test (one of: "
    + ", ".join(sorted(LAB_TEST_MAP)) + ", or null), gender "
    '("M", "F", or null). Output JSON only, no prose, no markdown fences.'
)


def _claude_parse(query: str) -> SearchFilter:
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            system=_CLAUDE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
        )
        text = msg.content[0].text.strip()
        data = json.loads(text)
        return SearchFilter(
            drug=data.get("drug"),
            missing_lab_test=data.get("missing_lab_test"),
            gender=data.get("gender"),
        )
    except Exception:
        # Same doctrine as every Claude call site in this portfolio: catch
        # Exception (not anthropic.APIError -- the SDK raises plain
        # TypeError on a missing key), fall back rather than 500.
        return _demo_parse(query)


def parse_query(query: str) -> SearchFilter:
    if DEMO_MODE:
        return _demo_parse(query)
    return _claude_parse(query)


def _lookback_days_for(drug: str | None, test_key: str) -> int:
    """A 'missing recent test' query means missing within some interval,
    not missing ever. If the drug+test pair matches a cited monitoring
    requirement, use its real interval; otherwise fall back to a generic
    UX default (config.DEFAULT_LOOKBACK_DAYS)."""
    if drug:
        for req in MONITORING_REQUIREMENTS:
            if req["drug"] in drug or drug in req["drug"]:
                if req["test_key"] == test_key:
                    return req["interval_days"]
    return DEFAULT_LOOKBACK_DAYS


def execute_filter(
    patients: list[MasterPatient],
    filt: SearchFilter,
    as_of: date | None = None,
) -> list[MasterPatient]:
    if as_of is None:
        as_of = date.today()
    results = []
    for p in patients:
        if filt.gender and p.gender != filt.gender:
            continue
        if filt.drug:
            has_drug = any(
                filt.drug in (m.get("drug_description") or "").lower()
                for m in p.medications
            )
            if not has_drug:
                continue
        if filt.missing_lab_test:
            last = most_recent_lab_date(p, filt.missing_lab_test)
            if last is not None:
                lookback = _lookback_days_for(filt.drug, filt.missing_lab_test)
                if (as_of - last).days <= lookback:
                    continue
        results.append(p)
    return results
