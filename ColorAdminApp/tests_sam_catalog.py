from pathlib import Path

from django.test import SimpleTestCase

from .sam_catalog import match_local_common, match_target, parse_catalog
from .management.commands.sync_sam_catalog import Command


class SamCatalogTests(SimpleTestCase):
    def test_parse_uses_stable_sam_id_and_removes_html(self):
        rows = {"rows": [{"cells": [
            "503771", "ALUNO TESTE", "VILA SANTA RITA <span></span> | BR-SP-ITAPEVI-ITAPEVI",
            "MÚSICO", "VIOLINO", "CULTO OFICIAL", "503771", "0",
        ]}]}
        student = parse_catalog(rows)[0]
        self.assertEqual(student["source_key"], "503771")
        self.assertEqual(student["common_name"], "VILA SANTA RITA")
        self.assertEqual(student["city"], "ITAPEVI")
        self.assertTrue(student["fingerprint"])

    def test_common_mapping_requires_unique_name_and_city(self):
        student = {"common_name": "São João", "city": "Itapevi"}
        commons = [
            {"comum": "BR-22-3510 - SÃO JOÃO", "cidade": "ITAPEVI"},
            {"comum": "BR-20-0001 - SÃO JOÃO", "cidade": "COTIA"},
        ]
        self.assertEqual(match_local_common(student, commons)["comum"], "BR-22-3510 - SÃO JOÃO")

    def test_target_match_refuses_ambiguous_names(self):
        student = {"name": "JOÃO DA SILVA"}
        targets = [{"id": "1", "nome_aluno": "JOÃO DA SILVA"}, {"id": "2", "nome_aluno": "JOAO DA SILVA"}]
        self.assertEqual(match_target(student, targets)[1], "ambiguous")

    def test_missing_states_excludes_students_seen_in_current_catalog(self):
        states = [
            {"id": "1", "source_key": "100"},
            {"id": "2", "source_key": "200"},
            {"id": "3", "source_key": "300", "missing_since": "2026-08-01T00:00:00Z"},
        ]
        self.assertEqual(
            [state["id"] for state in Command._missing_states(states, {"100", "300"})],
            ["2"],
        )

    def test_catalog_guard_rejects_abnormal_drop(self):
        self.assertTrue(Command._catalog_size_is_safe(4460, 4500))
        self.assertFalse(Command._catalog_size_is_safe(500, 4500))

    def test_catalog_reconciliation_uses_sam_id_and_source_location_fallback(self):
        command = Path(__file__).parent / "management" / "commands" / "sync_sam_catalog.py"
        content = command.read_text(encoding="utf-8")

        self.assertIn("targets_by_sam_id", content)
        self.assertIn('target or targets_by_sam_id.get(str(student["source_key"]))', content)
        self.assertIn('local_common["comum"] if local_common else student["common_name"]', content)
        self.assertIn('local_common.get("cidade") if local_common else student["city"]', content)
