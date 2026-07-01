"""dates.py — parses the date formats PatientFusion's silo CSVs actually
use for *clinical* fields (as opposed to patient DOB, which has its own
per-silo formats handled in entity_resolver.parse_dob). Conditions/ER use
plain ISO dates (YYYY-MM-DD); medications/labs use ISO datetimes
(YYYY-MM-DDTHH:MM:SSZ) inherited unmodified from Synthea's raw export."""
from __future__ import annotations

from datetime import date, datetime


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        if "T" in raw:
            return datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S").date()
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def age_on(dob: date, as_of: date) -> int:
    years = as_of.year - dob.year
    if (as_of.month, as_of.day) < (dob.month, dob.day):
        years -= 1
    return years
