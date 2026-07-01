"""models.py — plain dataclasses shared across PatientFusion. No logic."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MasterPatient:
    """A patient resolved across some subset of the four silos. Built by
    linkage.py; consumed by the decision engines, dashboard, and search."""

    patient_id: str
    first_name: str
    last_name: str
    dob: str
    gender: str
    conditions: list[dict] = field(default_factory=list)   # primary_care rows
    medications: list[dict] = field(default_factory=list)  # pharmacy rows
    labs: list[dict] = field(default_factory=list)          # labs rows
    er_visits: list[dict] = field(default_factory=list)     # er rows
    name_variants: set[tuple[str, str, str]] = field(default_factory=set)  # (silo, "first last", dob) seen

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def silos_present(self) -> list[str]:
        present = []
        if self.conditions:
            present.append("primary_care")
        if self.medications:
            present.append("pharmacy")
        if self.labs:
            present.append("labs")
        if self.er_visits:
            present.append("er")
        return present

    def add_row(self, silo: str, row: dict) -> None:
        if silo == "primary_care":
            self.conditions.append(row)
        elif silo == "pharmacy":
            self.medications.append(row)
        elif silo == "labs":
            self.labs.append(row)
        elif silo == "er":
            self.er_visits.append(row)
        variant_first = row.get("first_name", self.first_name)
        variant_last = row.get("last_name", self.last_name)
        variant_dob = row.get("dob", self.dob)
        self.name_variants.add((silo, f"{variant_first} {variant_last}", variant_dob))
