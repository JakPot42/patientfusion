"""Rich terminal dashboard — ASCII-safe for Windows cp1252 console."""
from __future__ import annotations

import json

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from models import MasterPatient

console = Console(width=110)

TIER_COLORS = {
    "LOW": "green",
    "MODERATE": "yellow",
    "HIGH": "red",
}

SEVERITY_COLORS = {
    "MODERATE": "yellow",
    "MAJOR": "bold red",
}

_BANNER = """
[bold cyan]PatientFusion[/bold cyan]  [dim]v1.0[/dim]
[bold yellow]SYNTHETIC DATA ONLY -- Synthea-generated patients. Not a clinical tool.[/bold yellow]
[dim]Fuzzy name+DOB record linkage across four fragmented health-record silos[/dim]
"""


def print_banner() -> None:
    console.print(_BANNER)


def print_resolve_stats(stats: dict) -> None:
    console.rule("[bold]Entity Resolution -- Cross-Silo Linkage[/bold]")
    t = Table(box=box.ASCII2, show_header=False)
    t.add_row("Silo identity records seen (pre-resolution)", str(stats["total_silo_identities"]))
    t.add_row("Master patients resolved", str(stats["master_patients"]))
    t.add_row("Records collapsed by linkage", str(stats["identities_collapsed"]))
    t.add_row("Patients linked across 2+ silos", str(stats["multi_silo_patients"]))
    t.add_row("Patients seen in only 1 silo", str(stats["single_silo_patients"]))
    console.print(t)


def print_patient_timeline(patient: MasterPatient, findings: dict) -> None:
    console.rule(f"[bold]{patient.full_name}[/bold]  ({patient.patient_id})")
    console.print(
        f"DOB: {patient.dob}   Gender: {patient.gender}   "
        f"Silos linked: {', '.join(patient.silos_present) or 'none'}"
    )
    if len(patient.name_variants) > 1:
        console.print("[dim]Name/DOB as captured per silo:[/dim]")
        for silo, name, dob in sorted(patient.name_variants):
            console.print(f"  [dim]{silo:<13} {name}  ({dob})[/dim]")

    events = []
    for c in patient.conditions:
        events.append((c.get("onset_date", ""), "primary_care", c.get("condition_description", "")))
    for m in patient.medications:
        events.append((m.get("start_date", "")[:10], "pharmacy", m.get("drug_description", "")))
    for lab in patient.labs:
        events.append((lab.get("test_date", "")[:10], "labs", f"{lab.get('test_key')} = {lab.get('value')} {lab.get('units')}"))
    for er in patient.er_visits:
        events.append((er.get("visit_date", ""), "er", f"{er.get('encounter_class')}: {er.get('chief_complaint')}"))
    events.sort(key=lambda e: e[0] or "")

    console.print()
    console.rule("Timeline")
    t = Table(box=box.ASCII2)
    t.add_column("Date")
    t.add_column("Silo")
    t.add_column("Event", overflow="fold")
    for dt, silo, desc in events:
        t.add_row(dt, silo, desc)
    console.print(t)

    console.print()
    console.rule("Decision Layer")
    if findings.get("drug_interactions"):
        console.print("[bold red]Drug Interactions:[/bold red]")
        for f in findings["drug_interactions"]:
            color = SEVERITY_COLORS.get(f["severity"], "white")
            console.print(f"  [{color}]{f['severity']}[/{color}] {f['drug_a']} + {f['drug_b']}")
            console.print(f"    {f['mechanism']}")
            console.print(f"    [dim]{f['citation']}[/dim]")
    else:
        console.print("[green]No drug interactions detected.[/green]")

    console.print()
    poly = findings.get("polypharmacy")
    if poly and poly["is_polypharmacy"]:
        console.print(
            f"[yellow]Polypharmacy: {poly['active_medication_count']} concurrent "
            f"medications (threshold {poly['threshold']}+)[/yellow]"
        )
    elif poly:
        console.print(f"[green]No polypharmacy: {poly['active_medication_count']} active medications.[/green]")

    console.print()
    if findings.get("overdue_screenings"):
        console.print("[bold yellow]Overdue Screenings:[/bold yellow]")
        for f in findings["overdue_screenings"]:
            console.print(f"  {f['label']} -- last: {f['last_test_date'] or 'never'}")
    if findings.get("monitoring_gaps"):
        console.print("[bold yellow]Monitoring Gaps:[/bold yellow]")
        for f in findings["monitoring_gaps"]:
            console.print(
                f"  On {f['drug']}, no {f['required_test']} in "
                f"{f['days_since_last_test'] if f['days_since_last_test'] is not None else 'ever'} days "
                f"(requires every {f['interval_days']})"
            )

    console.print()
    lace = findings.get("readmission_risk")
    if lace:
        color = TIER_COLORS.get(lace["risk_tier"], "white")
        console.print(
            f"Readmission risk (simplified LACE): "
            f"[{color}]{lace['lace_score']} -- {lace['risk_tier']}[/{color}]"
        )
    else:
        console.print("[dim]Readmission risk: no acute-care encounter on record.[/dim]")


def print_population_heatmap(rows: list[dict], top_n: int | None = None) -> None:
    console.rule("[bold]Population Risk Heatmap[/bold]")
    ordered = sorted(rows, key=lambda r: r["lace_score"] if r["lace_score"] is not None else -1, reverse=True)
    if top_n:
        ordered = ordered[:top_n]
    t = Table(box=box.ASCII2)
    t.add_column("Patient ID", overflow="fold")
    t.add_column("Name", overflow="fold")
    t.add_column("LACE", justify="right")
    t.add_column("Tier")
    t.add_column("Interact.", justify="right")
    t.add_column("Poly.")
    t.add_column("Gaps", justify="right")
    for r in ordered:
        tier = r["risk_tier"] or "N/A"
        color = TIER_COLORS.get(tier, "dim")
        t.add_row(
            r["patient_id"], r["name"],
            str(r["lace_score"]) if r["lace_score"] is not None else "-",
            f"[{color}]{tier}[/{color}]",
            str(r["interaction_count"]),
            "yes" if r["polypharmacy"] else "no",
            str(r["monitoring_gap_count"]),
        )
    console.print(t)


def print_search_results(query: str, filt_dict: dict, results: list[MasterPatient]) -> None:
    console.rule(f"[bold]Search:[/bold] \"{query}\"")
    console.print(f"[dim]Parsed filter: {filt_dict}[/dim]")
    console.print(f"[bold]{len(results)}[/bold] matching patient(s)")
    if results:
        t = Table(box=box.ASCII2)
        t.add_column("Patient ID", overflow="fold")
        t.add_column("Name", overflow="fold")
        t.add_column("DOB")
        t.add_column("Gender")
        for p in results:
            t.add_row(p.patient_id, p.full_name, p.dob, p.gender)
        console.print(t)


def print_json(data) -> None:
    console.print_json(json.dumps(data))
