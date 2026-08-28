from django.test import SimpleTestCase

from .sam_catalog import match_local_common, match_target, parse_catalog


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
