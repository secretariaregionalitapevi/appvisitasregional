import io
from unittest.mock import patch
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve
from openpyxl import Workbook
from . import music_exams

@override_settings(SUPABASE_URL="https://db.example",SUPABASE_SERVICE_ROLE_KEY="secret")
class MusicExamsTests(SimpleTestCase):
    def setUp(self):
        self.request=RequestFactory().post("/musica/exames/api/importar/")
        self.request.session={"user_profile":{"role_id":1,"full_name":"Gestor Teste"}}
        self.student={"id":"11111111-1111-1111-1111-111111111111","nome_aluno":"ANA TESTE","registro_msa":"123","municipio":"ITAPEVI","comum_congregacao":"CENTRAL","instrumento":"VIOLINO","cargo_ministerio":"MÚSICO"}
    def test_routes(self):
        self.assertEqual(resolve("/musica/exames/").url_name,"musicExams")
        self.assertEqual(resolve("/musica/exames/api/participantes/").url_name,"musicExamsParticipants")
    def test_idempotency_key_is_stable(self):
        p={"aluno_id":"1","nome_aluno":"Ána Teste","data_exame":"2026-08-15","tipo_exame":"Culto Oficial","instrumento":"Violino"}
        self.assertEqual(music_exams.idempotency_key(p),music_exams.idempotency_key(dict(p,nome_aluno="ANA TESTE")))
    @patch("ColorAdminApp.music_exams.visible_students")
    def test_reference_workbook_reads_sections(self,students):
        students.return_value=[self.student];book=Workbook();sheet=book.active
        sheet.append(["CONGREGAÇÃO CRISTÃ NO BRASIL"]);sheet.append(["RELAÇÃO DE MÚSICOS PARA PRÉ AVALIAÇÃO DE OFICIALIZAÇÃO",None,None,"DATA: 15/08/2026"]);sheet.append(["Nº","NOME","INSTRUMENTO","CONGREGAÇÃO","ENC: LOCAL","RESULTADO"]);sheet.append([1,"ANA TESTE","VIOLINO - DÓ","CENTRAL","RESPONSÁVEL","APROVADO"])
        stream=io.BytesIO();book.save(stream);stream.seek(0);items,unmatched=music_exams.parse_reference_workbook(stream,self.request)
        self.assertFalse(unmatched);self.assertEqual(items[0]["data_exame"],"2026-08-15");self.assertEqual(items[0]["tipo_exame"],"PRÉ-AVALIAÇÃO DE OFICIALIZAÇÃO");self.assertEqual(items[0]["resultado"],"APROVADO")
    def test_regional_groups(self):
        self.assertEqual(music_exams.regional_group("Jandira"),"JANDIRA")
        self.assertEqual(music_exams.regional_group("Vargem Grande Paulista"),"COTIA / CAUCAIA / VGP")
        self.assertEqual(music_exams.regional_group("Pirapora do Bom Jesus"),"SANTANA / PIRAPORA")
    def test_legacy_summary_uses_categories_not_broken_total(self):
        row={field:0 for field in music_exams.LEGACY_FIELDS}
        row.update({"municipio":"Itapevi","musicos_culto_oficial":7,"musicos_oficializacao":9,"musicos_troca_instrumento":8,"total_exames":67})
        groups,totals=music_exams.legacy_summary([row])
        self.assertEqual(groups[0]["total"],24)
        self.assertEqual(totals["total"],24)