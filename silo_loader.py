"""silo_loader.py — reads the four independent silo CSVs. No resolution
logic here; that's entity_resolver.py + linkage.py."""
from __future__ import annotations

import csv

from config import SILO_FILES


def load_silo(silo_name: str) -> list[dict]:
    """Returns every raw row from one silo's CSV, in file order."""
    path = SILO_FILES[silo_name]
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def group_by_identity(rows: list[dict]) -> list[dict]:
    """Groups a silo's rows by the (first_name, last_name, dob) triple that
    silo captured them under. Each silo re-captures a patient's demographics
    independently, so within one silo the same patient's rows always carry
    identical name/DOB (there's no re-randomization per visit) -- but across
    silos those triples can differ. This groups within a silo BEFORE cross-
    silo resolution, so entity_resolver compares one identity per patient
    per silo rather than one per clinical row.
    """
    groups: dict[tuple[str, str, str], dict] = {}
    for i, row in enumerate(rows):
        key = (row.get("first_name", ""), row.get("last_name", ""), row.get("dob", ""))
        if key not in groups:
            groups[key] = {
                "first_name": key[0],
                "last_name": key[1],
                "dob": key[2],
                "gender": row.get("gender", ""),
                "row_indices": [],
            }
        groups[key]["row_indices"].append(i)
    return list(groups.values())
