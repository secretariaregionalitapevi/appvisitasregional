from django.test import SimpleTestCase

from .sam_program import assess_program, instrument_group, target_for_level


class SamMinimumProgramTests(SimpleTestCase):
    def test_next_target_follows_current_level(self):
        self.assertEqual(target_for_level("CANDIDATO(A)"), "rjm")
        self.assertEqual(target_for_level("RJM / ENSAIO"), "culto")
        self.assertEqual(target_for_level("CULTO OFICIAL"), "oficializacao")

    def test_organ_is_detected_from_ministry_or_instrument(self):
        self.assertEqual(instrument_group("ÓRGÃO", "ORGANISTA"), "ORGAO")

    def test_documented_msa_without_method_and_hymnal_is_not_eligible(self):
        result = assess_program(
            {"nivel": "RJM", "instrumento": "VIOLINO", "cargo_ministerio": "MÚSICO"},
            {"msa": [{"fase": "16.1 - 16.3"}], "metodo": [], "hinario": []},
        )
        self.assertEqual(result["target"], "culto")
        self.assertFalse(result["eligible"])
        self.assertEqual([item["status"] for item in result["requirements"]], ["ok", "missing", "missing"])
        self.assertEqual(result["requirements"][0]["required"], "Fase mínima exigida para a etapa: 16")
        self.assertEqual(result["requirements"][0]["current"], "Fase alcançada no histórico: 16.3 (requisito superado)")

    def test_phase_16_3_is_not_reduced_to_phase_12(self):
        result = assess_program(
            {"nivel": "ENSAIO", "instrumento": "TROMPETE", "cargo_ministerio": "MÚSICO"},
            {"msa": [{"fase": "16.1 - 16.3"}], "metodo": [], "hinario": []},
        )
        msa = result["requirements"][0]
        self.assertEqual(msa["status"], "ok")
        self.assertEqual(msa["required"], "Fase mínima exigida para a etapa: 12")
        self.assertEqual(msa["current"], "Fase alcançada no histórico: 16.3 (requisito superado)")

    def test_consolidated_hymn_range_is_counted_but_method_requires_review(self):
        result = assess_program(
            {"nivel": "CANDIDATO(A)", "instrumento": "FLAUTA", "cargo_ministerio": "MÚSICO"},
            {
                "msa": [{"fase": "12.1"}],
                "metodo": [{"metodo": "Parès", "pagina": "41"}],
                "hinario": [{"hino": "431 a 480", "voz": "Soprano"}],
            },
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(result["status"], "review")
        self.assertEqual(result["requirements"][2]["status"], "ok")
    def test_culto_requires_full_instrument_specific_stage(self):
        student = {"nivel": "RJM", "instrumento": "VIOLINO", "cargo_ministerio": "MÚSICO"}
        records = {
            "msa": [{"fase": "16.3"}],
            "metodo": [{"metodo": "Método Facilitado Britten", "pagina": "55"}],
            "hinario": [{"hino": "1 a 480", "voz": "Principal e alternativa"}],
        }
        result = assess_program(student, records)
        self.assertTrue(result["eligible"])
        self.assertEqual(result["completion_percent"], 100)

        records["metodo"][0]["pagina"] = "54"
        result = assess_program(student, records)
        self.assertFalse(result["eligible"])
        self.assertLess(result["completion_percent"], 100)
