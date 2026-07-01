"""linkage.py — orchestrates entity resolution across all four silos and
assembles MasterPatient objects with their full cross-silo timeline.

This is the module that actually solves the fragmentation problem: no
silo shares a patient ID, so the only way to know that a primary_care
record, a pharmacy record, a labs record, and an er record describe the
same human is fuzzy name+DOB matching (entity_resolver.py).
"""
from __future__ import annotations

from entity_resolver import Adjudicator, resolve_patients
from models import MasterPatient
from silo_loader import group_by_identity, load_silo

SILO_ORDER = ["primary_care", "pharmacy", "labs", "er"]


def build_master_patients(
    adjudicator: Adjudicator | None = None,
) -> tuple[list[MasterPatient], dict]:
    """Loads all four silos, resolves identities across them, and returns
    (master_patients, stats). stats reports how much fragmentation was
    actually collapsed -- useful both for the CLI and for tests."""
    silo_rows: dict[str, list[dict]] = {}
    silo_groups: dict[str, list[dict]] = {}
    raw_records: list[dict] = []

    for silo in SILO_ORDER:
        rows = load_silo(silo)
        groups = group_by_identity(rows)
        silo_rows[silo] = rows
        silo_groups[silo] = groups
        for i, g in enumerate(groups):
            raw_records.append({**g, "silo": silo, "_index": i})

    masters, _assignment = resolve_patients(raw_records, adjudicator)

    result: list[MasterPatient] = []
    for n, m in enumerate(masters, start=1):
        mp = MasterPatient(
            patient_id=f"MP-{n:05d}",
            first_name=m["first_name"],
            last_name=m["last_name"],
            dob=m["dob"],
            gender=m["gender"],
        )
        for ref in m["silo_records"]:
            silo, group_idx = ref["silo"], ref["index"]
            group = silo_groups[silo][group_idx]
            for row_idx in group["row_indices"]:
                mp.add_row(silo, silo_rows[silo][row_idx])
        result.append(mp)

    stats = {
        "total_silo_identities": len(raw_records),
        "master_patients": len(result),
        "identities_collapsed": len(raw_records) - len(result),
        "multi_silo_patients": sum(1 for mp in result if len(mp.silos_present) > 1),
        "single_silo_patients": sum(1 for mp in result if len(mp.silos_present) <= 1),
    }
    return result, stats
