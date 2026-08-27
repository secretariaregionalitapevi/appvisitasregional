import json
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from .gem import _build_timeline, _milestones, academic_status, api_students, api_summary, is_graduated


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
