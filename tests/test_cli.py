"""End-to-end CLI tests against the real seeded Synthea demo data. No
network calls (DEMO_MODE=True is the default)."""
from __future__ import annotations

import os
import sys

from click.testing import CliRunner

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import cli


def _run(*args):
    runner = CliRunner()
    return runner.invoke(cli, args)


class TestResolveCommand:
    def test_exits_cleanly(self):
        result = _run("resolve")
        assert result.exit_code == 0
        assert "Master patients resolved" in result.output

    def test_no_adjudicate_flag(self):
        result = _run("resolve", "--no-adjudicate")
        assert result.exit_code == 0


class TestListCommand:
    def test_exits_cleanly(self):
        result = _run("list", "--limit", "3")
        assert result.exit_code == 0
        assert "MP-00001" in result.output


class TestTimelineCommand:
    def test_valid_patient_id(self):
        result = _run("timeline", "MP-00001")
        assert result.exit_code == 0
        assert "MP-00001" in result.output

    def test_unknown_patient_id_exits_nonzero(self):
        result = _run("timeline", "MP-99999")
        assert result.exit_code != 0


class TestHeatmapCommand:
    def test_table_format(self):
        result = _run("heatmap", "--top", "5")
        assert result.exit_code == 0
        assert "Population Risk Heatmap" in result.output

    def test_json_format_is_valid_json(self):
        import json
        result = _run("heatmap", "--format", "json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert "patient_id" in data[0]


class TestSearchCommand:
    def test_warfarin_inr_query(self):
        result = _run("search", "show me everyone on warfarin without a recent INR check")
        assert result.exit_code == 0
        assert "matching patient" in result.output

    def test_metformin_egfr_query(self):
        result = _run("search", "patients on metformin without a recent eGFR check")
        assert result.exit_code == 0


class TestDemoCommand:
    def test_runs_without_error(self):
        result = _run("demo")
        assert result.exit_code == 0
        assert "SYNTHETIC DATA ONLY" in result.output


class TestSyntheticDataFramingIsAlwaysVisible:
    def test_banner_appears_on_every_command(self):
        for args in (("resolve",), ("list",), ("heatmap",)):
            result = _run(*args)
            assert "SYNTHETIC DATA ONLY" in result.output
