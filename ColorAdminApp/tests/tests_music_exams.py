import io
from unittest.mock import patch
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve
from openpyxl import Workbook
from ColorAdminApp import music_exams

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
    def test_agenda_includes_only_musician_and_organist_exams(self):
        for title in [
            "Pr\u00e9-avalia\u00e7\u00e3o de M\u00fasicos (Itapevi)",
            "Pr\u00e9-avalia\u00e7\u00e3o de Organistas",
            "Avalia\u00e7\u00e3o de Organistas (Cotia)",
            "Exame de M\u00fasicos", "Exames de Organistas",
        ]:
            with self.subTest(title=title):
                self.assertTrue(music_exams.is_exam_agenda_event(title))
        for title in [
            "Reuni\u00e3o de Ensinamentos da Obra da Piedade",
            "Reuni\u00e3o Musical Geral", "Ensaio Regional",
            "Capacita\u00e7\u00e3o de Instrutoras", "Exame de outros departamentos",
            "Reuni\u00e3o sobre exames de m\u00fasicos", "",
        ]:
            with self.subTest(title=title):
                self.assertFalse(music_exams.is_exam_agenda_event(title))

    @patch("ColorAdminApp.music_exams.requests.post")
    def test_save_supports_database_before_agenda_columns(self, post):
        from unittest.mock import Mock
        missing = Mock(status_code=400)
        missing.json.return_value = {"code": "42703", "message": "column agenda_evento_id does not exist"}
        saved = Mock(status_code=201)
        saved.json.return_value = [{"id": "exam"}]
        post.side_effect = [missing, saved]
        payload = {"aluno_id": "student", "agenda_evento_id": "event", "agenda_evento_titulo": "Exame", "agenda_evento_data": "2026-09-19", "observacoes": "Original"}
        self.assertEqual(music_exams.save_exam(payload), {"id": "exam"})
        compatible = post.call_args.kwargs["json"]
        self.assertNotIn("agenda_evento_id", compatible)
        self.assertIn("Original", compatible["observacoes"])
        self.assertIn("ID: event", compatible["observacoes"])

    @patch("ColorAdminApp.music_exams.requests.patch")
    def test_approved_exam_advances_level_preserving_rjm(self, update):
        music_exams.update_student_stage(dict(self.student, nivel="RJM / CULTO OFICIAL"), {"tipo_exame": "OFICIALIZA\u00c7\u00c3O", "resultado": "APROVADO"})
        self.assertEqual(update.call_args.kwargs["json"], {"nivel": "RJM / OFICIALIZADO(A)"})
        update.reset_mock()
        for result in ["AUSENTE", "RETORNOU AO CICLO"]:
            music_exams.update_student_stage(dict(self.student, nivel="RJM"), {"tipo_exame": "CULTO OFICIAL", "resultado": result})
        music_exams.update_student_stage(dict(self.student, nivel="OFICIALIZADO(A)"), {"tipo_exame": "RJM", "resultado": "APROVADO"})
        update.assert_not_called()

    @patch("ColorAdminApp.music_exams.update_student_stage")
    @patch("ColorAdminApp.music_exams.save_exam")
    @patch("ColorAdminApp.music_exams.agenda_events")
    @patch("ColorAdminApp.music_exams.visible_students")
    @patch("ColorAdminApp.music_exams.sync_shared_exam")
    def test_save_links_selected_student_and_updates_progress(self, shared, students, agenda, save, sync):
        import json
        students.return_value = [self.student]
        agenda.return_value = [{"id": "event", "data": "2026-09-19", "titulo": "Exame de Musicos (Itapevi)", "hora": "09:30", "url": "https://ccbagenda.vercel.app/"}]
        save.side_effect = lambda payload: dict(payload, id="exam")
        request = RequestFactory().post("/musica/exames/api/registros/", data=json.dumps({"aluno_id": self.student["id"], "agenda_evento_id": "event", "tipo_exame": "OFICIALIZACAO", "resultado": "APROVADO"}), content_type="application/json")
        request.session = self.request.session
        response = music_exams.api_record(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(save.call_args.args[0]["aluno_id"], self.student["id"])
        sync.assert_called_once()

    @patch("ColorAdminApp.music_exams.requests.post")
    def test_unrelated_database_error_is_not_retried(self, post):
        from unittest.mock import Mock
        import requests
        failed = Mock(status_code=400)
        failed.json.return_value = {"code": "23514", "message": "invalid result"}
        failed.raise_for_status.side_effect = requests.HTTPError("invalid result")
        post.return_value = failed
        with self.assertRaises(requests.HTTPError):
            music_exams.save_exam({"agenda_evento_id": "event"})
        post.assert_called_once()

    @patch("ColorAdminApp.gem.can_open_module", return_value=True)
    @patch("ColorAdminApp.gem.requests.get")
    def test_student_timeline_contains_approved_exam_and_proof(self, get, access):
        import json
        from unittest.mock import Mock
        from ColorAdminApp.gem import api_student_timeline
        exam = {"id": "exam", "aluno_id": self.student["id"], "tipo_exame": "OFICIALIZACAO", "resultado": "APROVADO", "data_exame": "2026-09-19", "prova_url": "student/proof.jpeg", "prova_nome": "prova.jpeg"}
        def response(url, **kwargs):
            result = Mock()
            if url.endswith("/musica_acompanhamento_aluno"):
                result.json.return_value = [dict(self.student, nivel="OFICIALIZADO(A)")]
            elif url.endswith("/musica_exames_individuais"):
                result.json.return_value = [exam]
            else:
                result.json.return_value = []
            return result
        get.side_effect = response
        request = RequestFactory().get("/gem/api/alunos/student/linha-do-tempo/")
        request.session = self.request.session
        result = api_student_timeline(request, self.student["id"])
        self.assertEqual(result.status_code, 200)
        body = json.loads(result.content)
        self.assertEqual(body["music_exams"][0]["prova_nome"], "prova.jpeg")
        self.assertEqual(body["records"]["atividades"][0]["tipo_atividade"], "oficializacao")
        self.assertEqual(body["records"]["atividades"][0]["exam_id"], "exam")

    def test_dashboard_adds_new_exams_once_in_correct_region(self):
        baseline = [{"municipio": "Cotia", "musicos_oficializacao": 29}]
        exam = {"id": "one", "origem": "PAINEL", "municipio": "CAUCAIA DO ALTO", "categoria": "MUSICO", "tipo_exame": "OFICIALIZACAO", "resultado": "APROVADO"}
        groups, totals = music_exams.dashboard_summary(baseline, [exam, dict(exam), dict(exam, id="absent", resultado="AUSENTE"), dict(exam, id="import", origem="IMPORTACAO")])
        cotia = next(row for row in groups if row["grupo"] == "COTIA / CAUCAIA / VGP")
        self.assertEqual(cotia["musicos_oficializacao"], 30)
        self.assertEqual(totals["total"], 30)
        self.assertEqual(totals["musicos_total"], 30)

    def test_restores_agenda_date_and_title_from_saved_notes(self):
        row = music_exams.restore_agenda({"data_exame": "2026-09-19", "observacoes": "Agenda: Avaliacao de Musicos (Cotia) | 2026-09-19 09:30 | ID: abc123"})
        self.assertEqual(row["agenda_evento_data"], "2026-09-19")
        self.assertEqual(row["agenda_evento_titulo"], "Avaliacao de Musicos (Cotia)")
        self.assertEqual(row["agenda_evento_id"], "abc123")

    @patch("ColorAdminApp.music_exams.requests.delete")
    @patch("ColorAdminApp.music_exams.requests.get")
    def test_existing_exam_view_and_delete_validate_scope(self, get, delete):
        import json
        get.return_value.json.return_value = [dict(self.student, comum="CENTRAL", id="exam", data_exame="2026-09-19")]
        request = RequestFactory().get("/musica/exames/api/registros/exam/")
        request.session = self.request.session
        result = music_exams.api_record(request, "exam")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(json.loads(result.content)["item"]["data_exame"], "2026-09-19")
        request = RequestFactory().delete("/musica/exames/api/registros/exam/")
        request.session = self.request.session
        self.assertEqual(music_exams.api_record(request, "exam").status_code, 200)
        self.assertEqual(delete.call_count, 2)
        self.assertTrue(delete.call_args_list[0].args[0].endswith("/musica_exames_lancamentos"))
        self.assertTrue(delete.call_args_list[1].args[0].endswith("/musica_exames_individuais"))
        with patch("ColorAdminApp.music_exams.can_access", return_value=False):
            self.assertEqual(music_exams.api_record(request, "exam").status_code, 404)
        self.assertEqual(delete.call_count, 2)

    @patch("ColorAdminApp.music_exams.requests.patch")
    def test_edit_updates_original_exam_instead_of_inserting(self, update):
        update.return_value.json.return_value = [{"id": "same", "data_exame": "2026-10-15"}]
        result = music_exams.save_exam({"data_exame": "2026-10-15"}, "same")
        self.assertEqual(result["id"], "same")
        self.assertEqual(update.call_args.kwargs["params"], {"id": "eq.same"})

    def test_summary_tracks_create_edit_delete_and_external_launches(self):
        baseline = [{"municipio": "Cotia", "musicos_oficializacao": 29}]
        panel = {"id": "panel", "origem": "PAINEL", "municipio": "CAUCAIA DO ALTO", "categoria": "MUSICO", "tipo_exame": "OFICIALIZACAO", "resultado": "APROVADO"}
        def group(rows, city="COTIA / CAUCAIA / VGP"):
            groups, totals = music_exams.dashboard_summary(baseline, rows)
            return next(row for row in groups if row["grupo"] == city), totals
        self.assertEqual(group([])[0]["musicos_oficializacao"], 29)
        self.assertEqual(group([panel])[0]["musicos_oficializacao"], 30)
        edited = dict(panel, tipo_exame="CULTO OFICIAL")
        row, totals = group([edited])
        self.assertEqual(row["musicos_oficializacao"], 29)
        self.assertEqual(row["musicos_culto_oficial"], 1)
        self.assertEqual(totals["total"], 30)
        self.assertEqual(group([])[1]["total"], 29)
        external = dict(panel, id="external", origem="APP_EXAMES")
        self.assertEqual(group([panel, external])[0]["musicos_oficializacao"], 31)
        self.assertEqual(group([external])[0]["musicos_oficializacao"], 30)

    @patch("ColorAdminApp.music_exams.requests.post")
    def test_shared_launch_uses_exam_id_and_replaces_counts_on_edit(self, post):
        exam = {"id": "exam", "origem": "PAINEL", "municipio": "Cotia", "data_exame": "2026-09-19", "categoria": "MUSICO", "tipo_exame": "OFICIALIZACAO", "resultado": "APROVADO"}
        music_exams.sync_shared_exam(exam)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["id"], "exam")
        self.assertEqual(payload["musicos_oficializacao"], 1)
        self.assertEqual(payload["total_exames"], 1)
        music_exams.sync_shared_exam(dict(exam, tipo_exame="CULTO OFICIAL"))
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["id"], "exam")
        self.assertEqual(payload["musicos_oficializacao"], 0)
        self.assertEqual(payload["musicos_culto_oficial"], 1)

    def test_shared_mirror_does_not_double_count_individual(self):
        exam = {"id": "exam", "origem": "PAINEL", "municipio": "Cotia", "categoria": "MUSICO", "tipo_exame": "OFICIALIZACAO", "resultado": "APROVADO"}
        groups, totals = music_exams.dashboard_summary([{"id": "baseline", "municipio": "Cotia", "musicos_oficializacao": 29}, {"id": "exam", "municipio": "Cotia", "musicos_oficializacao": 1}], [exam])
        self.assertEqual(totals["musicos_oficializacao"], 30)
        self.assertEqual(totals["total"], 30)

    def test_agenda_matches_exam_hubs(self):
        for city, venue in [("CAUCAIA DO ALTO", "Cotia"), ("VARGEM GRANDE PAULISTA", "Cotia"), ("VGP", "Cotia"), ("PIRAPORA DO BOM JESUS", "Fazendinha"), ("SANTANA DE PARNAIBA", "Santana de Parnaiba"), ("ITAPEVI", "Itapevi"), ("JANDIRA", "Jandira")]:
            with self.subTest(city=city):
                self.assertTrue(music_exams.event_matches_municipality({"titulo": "Exame de Musicos ("+venue+")"}, city))
                self.assertFalse(music_exams.event_matches_municipality({"titulo": "Exame de Musicos (Outra cidade)"}, city))
        self.assertFalse(music_exams.event_matches_municipality({"titulo": "Exame de Musicos (Cotia)"}, ""))

    @patch("ColorAdminApp.music_exams.sync_shared_exam")
    @patch("ColorAdminApp.music_exams.update_student_stage")
    @patch("ColorAdminApp.music_exams.save_exam")
    @patch("ColorAdminApp.music_exams.agenda_events", return_value=[])
    @patch("ColorAdminApp.music_exams.visible_students")
    @patch("ColorAdminApp.music_exams.requests.get")
    def test_edit_preserves_saved_event_when_form_omits_selection(self, get, students, agenda, save, stage, shared):
        import json
        students.return_value = [self.student]
        existing = dict(self.student, id="exam", aluno_id=self.student["id"], comum="CENTRAL", data_exame="2026-09-19", prova_url="proof.jpeg", observacoes="Agenda: Exame de Musicos (Itapevi) | 2026-09-19 09:30 | ID: abc123")
        get.return_value.json.return_value = [existing]
        save.side_effect = lambda payload, record_id: dict(payload, id=record_id)
        for notes in [existing["observacoes"], "Sem vinculo com agenda"]:
            existing["observacoes"] = notes
            request = RequestFactory().post("/musica/exames/api/registros/exam/", data=json.dumps({"aluno_id": self.student["id"], "tipo_exame": "CULTO OFICIAL", "resultado": "APROVADO", "agenda_evento_id": ""}), content_type="application/json")
            request.session = self.request.session
            response = music_exams.api_record(request, "exam")
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(save.call_args.args[0]["data_exame"], "2026-09-19")
            self.assertEqual(save.call_args.args[0]["prova_url"], "proof.jpeg")

    def test_agenda_restore_uses_latest_saved_event(self):
        row = music_exams.restore_agenda({"observacoes": "Agenda: Antigo | 2026-08-01 09:30 | ID: aaa111\nAgenda: Atual | 2026-09-19 08:00 | ID: bbb222"})
        self.assertEqual(row["agenda_evento_id"], "bbb222")

    def test_agenda_notes_use_brazilian_dates_and_remove_duplicates(self):
        notes = "Minha observacao\nAgenda: Exame | 2026-09-19 09:30 | ID: abc123\nAgenda: Exame | 2026-09-19 09:30 | ID: abc123"
        restored = music_exams.restore_agenda({"observacoes": notes})
        self.assertEqual(restored["observacoes"].count("Agenda:"), 1)
        self.assertIn("19/09/2026 09:30", restored["observacoes"])
        self.assertIn("Minha observacao", restored["observacoes"])
        self.assertEqual(restored["agenda_evento_data"], "2026-09-19")
        self.assertEqual(music_exams.restore_agenda(restored), restored)

    def test_rjm_and_emergency_counts_are_exclusive_to_organists(self):
        exams = [{"id": str(i), "origem": "PAINEL", "municipio": "Cotia", "categoria": category, "tipo_exame": kind, "resultado": "APROVADO"} for i, (category, kind) in enumerate([("MUSICO", "RJM"), ("MUSICO", "TESTE EMERGENCIAL"), ("ORGANISTA", "RJM"), ("ORGANISTA", "TESTE EMERGENCIAL"), ("ORGANISTA", "TESTE ESPECIAL")])]
        groups, totals = music_exams.dashboard_summary([], exams)
        self.assertEqual(totals["musicos_total"], 0)
        self.assertEqual(totals["organistas_rjm"], 1)
        self.assertEqual(totals["organistas_testes_especiais"], 2)
        self.assertEqual(totals["total"], 3)

    def test_only_approval_counts_after_return_to_cycle_and_retake(self):
        baseline = [{"municipio": "Santana de Parnaiba", "organistas_oficializacao": 4}]
        returned = {"id": "attempt1", "aluno_id": "student", "origem": "PAINEL", "municipio": "Santana de Parnaiba", "categoria": "ORGANISTA", "tipo_exame": "OFICIALIZACAO", "resultado": "RETORNOU AO CICLO"}
        approved = dict(returned, id="attempt2", resultado="APROVADO")
        self.assertEqual(music_exams.dashboard_summary(baseline, [returned])[1]["organistas_oficializacao"], 4)
        self.assertEqual(music_exams.dashboard_summary(baseline, [returned, approved])[1]["organistas_oficializacao"], 5)
        self.assertEqual(music_exams.dashboard_summary(baseline, [dict(approved, resultado="RETORNOU AO CICLO")])[1]["total"], 4)

    @patch("ColorAdminApp.music_exams.requests.post")
    def test_shared_summary_clears_counts_when_result_returns_to_cycle(self, post):
        exam = {"id": "attempt", "municipio": "Santana de Parnaiba", "data_exame": "2026-10-24", "categoria": "ORGANISTA", "tipo_exame": "OFICIALIZACAO", "resultado": "RETORNOU AO CICLO"}
        music_exams.sync_shared_exam(exam)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["total_exames"], 0)
        self.assertTrue(all(payload[field] == 0 for field in music_exams.LEGACY_FIELDS))
