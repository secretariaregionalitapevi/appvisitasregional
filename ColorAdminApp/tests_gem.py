import json
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from .gem import (
    _build_timeline, _milestones, _program_progress, academic_status, api_student_record,
    api_students, api_summary, is_graduated,
)


def request_with_profile(path, profile, params=None):
    request = RequestFactory().get(path, data=params or {})
    request.session = {"authenticated": True, "user_profile": profile}
    return request


@override_settings(SUPABASE_URL="https://db.example", SUPABASE_SERVICE_ROLE_KEY="secret")
class GemTests(SimpleTestCase):
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

    def test_milestones_distinguish_achieved_current_and_future(self):
        milestones = _milestones("RJM / ENSAIO")
        self.assertEqual([item["status"] for item in milestones], ["achieved", "achieved", "current", "future", "future"])

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
