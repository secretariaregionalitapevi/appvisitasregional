import json
from datetime import date
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart

from .gem import (
    INSTRUMENT_OPTIONS, LEVEL_OPTIONS, MINISTRY_OPTIONS, TONALITY_OPTIONS, _build_timeline, _milestones, _operational_activity, _program_progress, academic_status,
    api_student_record, api_students, api_summary, is_graduated, operational_status_from_days, ordered_instrument_options,
)


def request_with_profile(path, profile, params=None):
    request = RequestFactory().get(path, data=params or {})
    request.session = {"authenticated": True, "user_profile": profile}
    return request


@override_settings(SUPABASE_URL="https://db.example", SUPABASE_SERVICE_ROLE_KEY="secret")
class GemTests(SimpleTestCase):
    def test_instrument_filter_uses_pedagogical_order(self):
        values = {"CLARINETE", "VIOLONCELO", "VIOLINO", "VIOLA", "BARÍTONO DE PISTO"}
        self.assertEqual(
            ordered_instrument_options(values),
            ["VIOLINO", "VIOLA", "VIOLONCELO", "CLARINETE", "BARÍTONO DE PISTO"],
        )
    def setUp(self):
        self.rows = [
            {"id": "1", "nome_aluno": "Ana", "nivel": "CANDIDATO(A)", "municipio": "ITAPEVI", "comum_congregacao": "CENTRAL", "instrumento": "VIOLINO", "programa_minimo_percentual": 25},
            {"id": "2", "nome_aluno": "Bia", "nivel": "RJM / OFICIALIZADO(A)", "municipio": "ITAPEVI", "comum_congregacao": "CENTRAL", "instrumento": "VIOLA", "programa_minimo_percentual": 100},
            {"id": "3", "nome_aluno": "Caio", "nivel": "CULTO OFICIAL", "municipio": "JANDIRA", "comum_congregacao": "JARDIM", "instrumento": "TROMPETE", "programa_minimo_percentual": 100},
        ]
        self.regional = {"role_id": 2, "sector": "Musicalização", "access_level": "regional"}

    def test_officialized_composite_level_is_graduated(self):
        self.assertTrue(is_graduated({"nivel": "RJM / OFICIALIZADO(A)"}))
        self.assertEqual(academic_status({"nivel": "OFICIALIZADA"}), "graduado")
        self.assertFalse(is_graduated({"nivel": "CULTO OFICIAL"}))

    def test_registration_catalog_has_all_official_levels(self):
        self.assertEqual(LEVEL_OPTIONS, [
            'CANDIDATO(A)', 'CULTO OFICIAL', 'ENSAIO', 'MEIA HORA', 'OFICIALIZADO(A)', 'RJM',
            'RJM / CULTO OFICIAL', 'RJM / ENSAIO', 'RJM / MEIA HORA', 'RJM / OFICIALIZADO(A)',
        ])

    def test_organ_is_instrument_and_organist_is_ministry(self):
        self.assertIn('ÓRGÃO', INSTRUMENT_OPTIONS)
        self.assertNotIn('ORGANISTA', INSTRUMENT_OPTIONS)
        self.assertIn('ORGANISTA', MINISTRY_OPTIONS)

    def test_milestones_distinguish_achieved_current_and_future(self):
        milestones = _milestones("RJM / ENSAIO")
        self.assertEqual([item["status"] for item in milestones], ["achieved", "achieved", "current", "future", "future"])
        self.assertEqual([item["title"] for item in milestones], [
            "Início dos estudos", "Ingresso no Ensaio", "Ingresso na RJM", "Culto Oficial", "Oficialização",
        ])

    def test_ensaio_is_an_explicit_current_milestone(self):
        milestones = _milestones("ENSAIO")
        self.assertEqual([item["status"] for item in milestones], ["achieved", "current", "future", "future", "future"])

    def test_timeline_combines_sources_in_reverse_date_order(self):
        events = _build_timeline(
            {"created_at": "2026-01-01T10:00:00"},
            {
                "msa": [{"data_aula": "2026-02-01", "fase": "Fase 2"}],
                "metodo": [], "hinario": [], "provas": [], "escalas": [],
                "atividades": [{"data_atividade": "2026-03-01", "titulo": "Ingresso no Ensaio"}],
            },
        )
        self.assertEqual([event["title"] for event in events], ["Ingresso no Ensaio", "MSA", "Início do acompanhamento"])

    def test_program_progress_uses_highest_known_msa_phase(self):
        self.assertEqual(_program_progress({"programa_minimo_percentual": 0}, [{"fase": "15.1"}]), 6)
        self.assertEqual(_program_progress({}, [{"fase": "Fase(s): de 1.1 até 16.3"}]), 0)
        documented = [{"fase": label} for label in (
            "1.1 - 1.4", "2.1 - 2.6", "3.1 - 3.4", "4.1 - 4.5",
            "4.6 - 5.2", "5.3 - 6.1", "6.2 - 6.6", "6.7 - 7.3",
            "7.4 - 8.1", "8.2 - 11.2", "11.3 - 12.2", "12.3 - 13.2",
            "13.3 - 14.2", "14.3 - 15.2", "15.3 - 15.6", "15.7 - 16.3",
        )]
        self.assertEqual(_program_progress({}, documented), 100)

    def test_operational_status_uses_sam_activity_age(self):
        self.assertEqual(operational_status_from_days(90), "ATIVO")
        self.assertEqual(operational_status_from_days(91), "ALERTA")
        self.assertEqual(operational_status_from_days(180), "ALERTA")
        self.assertEqual(operational_status_from_days(181), "INATIVO")
        self.assertEqual(operational_status_from_days(None), "SEM HISTORICO")
        activity = _operational_activity(
            {"msa": [{"data_aula": "2025-01-01"}], "provas": [{"data_prova": "2025-07-01"}]},
            today=date(2026, 8, 29),
        )
        self.assertEqual(activity["last_activity_at"], "2025-07-01")
        self.assertEqual(activity["operational_status"], "INATIVO")
        self.assertTrue(activity["requires_review"])

    @patch("ColorAdminApp.gem._fetch_students")
    def test_summary_separates_formation_from_graduates(self, fetch_students):
        fetch_students.return_value = self.rows
        response = api_summary(request_with_profile("/gem/api/resumo/", self.regional))
        payload = json.loads(response.content)
        self.assertEqual(payload["totals"]["formation"], 2)
        self.assertEqual(payload["totals"]["graduates"], 1)
        self.assertEqual(payload["totals"]["program_complete"], 1)

    @patch("ColorAdminApp.gem.requests.get")
    def test_default_student_list_excludes_graduates(self, mock_get):
        source_response = Mock(headers={"Content-Range": "0-1/2"})
        source_response.raise_for_status.return_value = None
        source_response.json.return_value = [self.rows[0], self.rows[2]]
        mock_get.return_value = source_response
        response = api_students(request_with_profile("/gem/api/alunos/", self.regional))
        payload = json.loads(response.content)
        self.assertEqual([row["nome_aluno"] for row in payload["items"]], ["Ana", "Caio"])
        self.assertEqual(mock_get.call_args.kwargs["params"]["nivel"], "not.ilike.*OFICIALIZAD*")

    @patch('ColorAdminApp.gem.requests.post')
    def test_student_create_sends_approved_fields_with_scope_and_lgpd(self, mock_post):
        saved = Mock(); saved.raise_for_status.return_value = None; saved.json.return_value = [{'id': 'novo'}]; mock_post.return_value = saved
        payload = {'nome_aluno': 'Ana Maria Teste', 'municipio': 'ITAPEVI', 'comum_congregacao': 'CENTRAL', 'cargo_ministerio': MINISTRY_OPTIONS[0], 'nivel': 'CANDIDATO(A)', 'instrumento': 'VIOLINO', 'tonalidade': TONALITY_OPTIONS[0], 'telefone': '(11) 99999-9999', 'consentimento_lgpd': True, 'possui_instrumento': True, 'instrumento_proprio': False}
        request = RequestFactory().post('/gem/api/alunos/', data=json.dumps(payload), content_type='application/json'); request.session = {'authenticated': True, 'user_profile': self.regional}
        response = api_students(request)
        self.assertEqual(response.status_code, 201)
        sent = mock_post.call_args.kwargs['json']
        self.assertEqual(sent['nome_aluno'], 'ANA MARIA TESTE')
        self.assertEqual(sent['telefone'], '11999999999')
        self.assertTrue(sent['consentimento_lgpd'])

    @patch('ColorAdminApp.gem.requests.post')
    def test_student_create_requires_lgpd_consent(self, mock_post):
        payload = {'nome_aluno': 'Ana Maria', 'municipio': 'ITAPEVI', 'comum_congregacao': 'CENTRAL', 'cargo_ministerio': MINISTRY_OPTIONS[0], 'nivel': 'CANDIDATO(A)', 'instrumento': 'VIOLINO', 'consentimento_lgpd': False}
        request = RequestFactory().post('/gem/api/alunos/', data=json.dumps(payload), content_type='application/json'); request.session = {'authenticated': True, 'user_profile': self.regional}
        response = api_students(request)
        self.assertEqual(response.status_code, 400)
        mock_post.assert_not_called()

    @patch('ColorAdminApp.gem.requests.post')
    def test_student_create_requires_responsible_for_minor(self, mock_post):
        payload = {'nome_aluno': 'Aluno Menor', 'municipio': 'ITAPEVI', 'comum_congregacao': 'CENTRAL', 'cargo_ministerio': MINISTRY_OPTIONS[0], 'nivel': 'CANDIDATO(A)', 'instrumento': 'VIOLINO', 'data_nascimento': '2015-01-01', 'consentimento_lgpd': True}
        request = RequestFactory().post('/gem/api/alunos/', data=json.dumps(payload), content_type='application/json'); request.session = {'authenticated': True, 'user_profile': self.regional}
        response = api_students(request)
        self.assertEqual(response.status_code, 400)
        mock_post.assert_not_called()

    @patch("ColorAdminApp.access_control.common_catalog", return_value=[])
    @patch("ColorAdminApp.gem.requests.get")
    def test_local_scope_never_exposes_another_common(self, mock_get, _catalog):
        source_response = Mock(headers={"Content-Range": "0-1/2"})
        source_response.raise_for_status.return_value = None
        source_response.json.return_value = self.rows[:2]
        mock_get.return_value = source_response
        profile = {"role_id": 4, "sector": "Musicalização", "access_level": "local", "comum": "CENTRAL", "municipio": "ITAPEVI"}
        response = api_students(request_with_profile("/gem/api/alunos/", profile, {"situacao": "todos"}))
        payload = json.loads(response.content)
        self.assertEqual([row["nome_aluno"] for row in payload["items"]], ["Ana", "Bia"])
        self.assertEqual(mock_get.call_args.kwargs["params"]["comum_congregacao"], "eq.CENTRAL")

    @patch("ColorAdminApp.gem.requests.patch")
    @patch("ColorAdminApp.gem.requests.get")
    def test_record_edit_only_sends_allowed_fields_after_scope_check(self, mock_get, mock_patch):
        record_response = Mock()
        record_response.raise_for_status.return_value = None
        record_response.json.return_value = [{"id": "10", "aluno_id": "1", "fase": "1.1"}]
        student_response = Mock()
        student_response.raise_for_status.return_value = None
        student_response.json.return_value = [{"id": "1", "comum_congregacao": "CENTRAL", "municipio": "ITAPEVI"}]
        mock_get.side_effect = [record_response, student_response]
        saved_response = Mock()
        saved_response.raise_for_status.return_value = None
        saved_response.json.return_value = [{"id": "10", "aluno_id": "1", "fase": "2.1"}]
        mock_patch.return_value = saved_response
        request = RequestFactory().patch(
            "/gem/api/lancamentos/msa/10/",
            data=json.dumps({"fase": "2.1", "aluno_id": "outro", "campo_invalido": "x"}),
            content_type="application/json",
        )
        request.session = {"authenticated": True, "user_profile": self.regional}

        response = api_student_record(request, "msa", "10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_patch.call_args.kwargs["json"], {"fase": "2.1"})

    @patch("ColorAdminApp.gem.requests.patch")
    @patch("ColorAdminApp.gem.requests.post")
    @patch("ColorAdminApp.gem.requests.get")
    def test_activity_document_upload_parses_multipart_patch(self, mock_get, mock_post, mock_patch):
        record_response = Mock()
        record_response.raise_for_status.return_value = None
        record_response.json.return_value = [{"id": "10", "aluno_id": "1", "documento_url": None, "nome_documento": None}]
        student_response = Mock()
        student_response.raise_for_status.return_value = None
        student_response.json.return_value = [{"id": "1", "comum_congregacao": "CENTRAL", "municipio": "ITAPEVI"}]
        mock_get.side_effect = [record_response, student_response]
        mock_post.return_value.raise_for_status.return_value = None
        saved_response = Mock()
        saved_response.raise_for_status.return_value = None
        saved_response.json.return_value = [{"id": "10", "aluno_id": "1", "documento_url": "1/arquivo.pdf", "nome_documento": "Carta personalizada.pdf"}]
        mock_patch.return_value = saved_response
        document = SimpleUploadedFile("original.pdf", b"%PDF-test", content_type="application/pdf")
        body = encode_multipart(BOUNDARY, {"aluno_id": "1", "nome_documento": "Carta personalizada.pdf", "documento": document})
        request = RequestFactory().generic("PATCH", "/gem/api/lancamentos/atividades/10/", data=body, content_type=MULTIPART_CONTENT)
        request.session = {"authenticated": True, "user_profile": self.regional}

        response = api_student_record(request, "atividades", "10")

        self.assertEqual(response.status_code, 200)
        payload = mock_patch.call_args.kwargs["json"]
        self.assertEqual(payload["nome_documento"], "Carta personalizada.pdf")
        self.assertTrue(payload["documento_url"].startswith("1/"))
        self.assertTrue(mock_post.called)
    @patch("ColorAdminApp.gem.requests.delete")
    @patch("ColorAdminApp.gem.requests.patch")
    @patch("ColorAdminApp.gem.requests.get")
    def test_activity_document_can_be_removed_without_deleting_record(self, mock_get, mock_patch, mock_delete):
        record_response = Mock()
        record_response.raise_for_status.return_value = None
        record_response.json.return_value = [{"id": "10", "aluno_id": "1", "documento_url": "1/carta.pdf", "nome_documento": "Carta.pdf"}]
        student_response = Mock()
        student_response.raise_for_status.return_value = None
        student_response.json.return_value = [{"id": "1", "comum_congregacao": "CENTRAL", "municipio": "ITAPEVI"}]
        mock_get.side_effect = [record_response, student_response]
        saved_response = Mock()
        saved_response.raise_for_status.return_value = None
        saved_response.json.return_value = [{"id": "10", "aluno_id": "1", "documento_url": None, "nome_documento": None}]
        mock_patch.return_value = saved_response
        mock_delete.return_value.raise_for_status.return_value = None
        request = RequestFactory().patch(
            "/gem/api/lancamentos/atividades/10/",
            data=json.dumps({"remover_documento": True}),
            content_type="application/json",
        )
        request.session = {"authenticated": True, "user_profile": self.regional}

        response = api_student_record(request, "atividades", "10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_patch.call_args.kwargs["json"], {"documento_url": None, "nome_documento": None})
        self.assertIn("/storage/v1/object/gem_documents/1/carta.pdf", mock_delete.call_args.args[0])
    @patch("ColorAdminApp.gem.requests.post")
    @patch("ColorAdminApp.gem.requests.get")
    def test_record_create_links_student_and_location(self, mock_get, mock_post):
        student_response = Mock()
        student_response.raise_for_status.return_value = None
        student_response.json.return_value = [{"id": "1", "comum_congregacao": "CENTRAL", "municipio": "ITAPEVI"}]
        mock_get.return_value = student_response
        saved_response = Mock()
        saved_response.raise_for_status.return_value = None
        saved_response.json.return_value = [{"id": "11", "aluno_id": "1", "fase": "3.1"}]
        mock_post.return_value = saved_response
        request = RequestFactory().post(
            "/gem/api/lancamentos/msa/",
            data=json.dumps({"aluno_id": "1", "fase": "3.1"}), content_type="application/json",
        )
        request.session = {"authenticated": True, "user_profile": self.regional}

        response = api_student_record(request, "msa")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(mock_post.call_args.kwargs["json"]["comum_congregacao"], "CENTRAL")
