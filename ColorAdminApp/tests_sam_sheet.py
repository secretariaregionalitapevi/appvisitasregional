from django.test import SimpleTestCase

from .sam_sheet import normalize_date, rows_to_export


class SamSheetTests(SimpleTestCase):
    def test_normalize_date_accepts_sam_formats(self):
        self.assertEqual(normalize_date("27/08/2026"), "2026-08-27")
        self.assertEqual(normalize_date("2026-08-27"), "2026-08-27")
        self.assertEqual(normalize_date(""), "")

    def test_rows_become_importable_history(self):
        document = rows_to_export([{
            "Nome": "Aluno Teste", "Instrumento": "Violino", "Localidade": "Central",
            "MSA Lancamento": "01/08/2026", "Fase MSA": "Fase 3",
            "Data Metodo": "02/08/2026", "Licoes do Metodo": "1 a 5", "Tipo Metodo": "Método A",
            "Hino": "431", "Data Hino": "03/08/2026",
        }])
        history = document["students"][0]["history"]
        self.assertEqual(history["msa"][0]["data_aula"], "2026-08-01")
        self.assertEqual(history["metodo"][0]["licao"], "1 a 5")
        self.assertEqual(history["hinario"][0]["hino"], "431")
