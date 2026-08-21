import json
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from .access_control import can_access, filter_rows, user_scope
from .admin_views import administration, administration_data, administration_user
from .middleware import SupabaseAuthMiddleware
from .views import apiAuth, apiRoteiroBairros, apiVisitas, apiVisitasAgenda, apiVisitasEquipes, apiVisitasIrmandade, apply_actual_visit_times, format_display_name, normalize_team_name, normalize_visit_team, unique_member_for_orphan_visit, userRegisterV3, visitasAgenda, visitasCadastro, visitasMapa, visitasNavegar, visitasRelatoriosEquipes
from .utils.routing import auto_dispatch_visits, clean_visit_address, group_route_visits_by_address, limit_daily_route, optimize_route, order_route_chronologically, route_address_key, street_key

CATALOG = [
    {"comum": "BR-01 - CENTRAL ITAPEVI", "cidade": "ITAPEVI"},
    {"comum": "BR-02 - JARDIM JANDIRA", "cidade": "JANDIRA"},
    {"comum": "BR-03 - ALTO ITAPEVI", "cidade": "ITAPEVI"},
]


class ActualVisitTimeTests(TestCase):
    def test_mobile_actual_times_replace_calendar_times_on_same_local_date(self):
        visit = {
            'data_inicio': '2026-08-19T23:00:00+00:00',
            'data_fim': '2026-08-20T00:00:00+00:00',
        }

        apply_actual_visit_times(visit, {'inicio': '14:35', 'fim': '15:00'})

        self.assertEqual(visit['data_inicio'], '2026-08-19T14:35:00-03:00')
        self.assertEqual(visit['data_fim'], '2026-08-19T15:00:00-03:00')

    def test_original_calendar_times_remain_without_mobile_actual_times(self):
        visit = {
            'data_inicio': '2026-08-19T23:00:00+00:00',
            'data_fim': '2026-08-20T00:00:00+00:00',
        }

        apply_actual_visit_times(visit, {})

        self.assertEqual(visit['data_inicio'], '2026-08-19T23:00:00+00:00')
        self.assertEqual(visit['data_fim'], '2026-08-20T00:00:00+00:00')


class HeaderBrotherhoodSearchTests(TestCase):
    def test_header_search_uses_safe_get_request_with_named_query(self):
        request = RequestFactory().get('/', {'q': 'Rutinha'})

        html = render_to_string('partial/header.html', {'request': request})

        self.assertIn('action="/visitas/cadastro/"', html)
        self.assertIn('method="GET"', html)
        self.assertIn('name="q"', html)
        self.assertNotIn('method="POST" name="search"', html)


class OrphanVisitReconciliationTests(TestCase):
    def test_matches_unique_recreated_member_by_exact_name_and_address(self):
        visit = {'titulo': 'Joaninha de Jesus', 'endereco_visitado': 'Estrada Velha da Olaria, 125'}
        members = [
            {'id': 'new-id', 'nome': 'Joaninha de Jesus', 'endereco': 'Estrada Velha da Olaria, 125'},
            {'id': 'other-id', 'nome': 'Outra Pessoa', 'endereco': 'Estrada Velha da Olaria, 125'},
        ]

        matched = unique_member_for_orphan_visit(visit, members)

        self.assertEqual(matched['id'], 'new-id')

    def test_does_not_guess_when_name_and_address_are_duplicated(self):
        visit = {'titulo': 'Maria', 'endereco_visitado': 'Rua A, 10'}
        members = [
            {'id': 'maria-1', 'nome': 'Maria', 'endereco': 'Rua A, 10'},
            {'id': 'maria-2', 'nome': 'Maria', 'endereco': 'Rua A, 10'},
        ]

        self.assertIsNone(unique_member_for_orphan_visit(visit, members))

    def test_matches_unique_full_name_when_address_changed(self):
        visit = {'titulo': 'Joaninha de Jesus', 'endereco_visitado': 'Estrada Velha da Olaria, 125'}
        members = [
            {'id': 'new-id', 'nome': 'Joaninha de Jesus', 'endereco': 'Estrada Velha da Olaria, 154'},
            {'id': 'other-id', 'nome': 'Outra Pessoa', 'endereco': 'Estrada Velha da Olaria, 125'},
        ]

        matched = unique_member_for_orphan_visit(visit, members)

        self.assertEqual(matched['id'], 'new-id')


class VisitNavigationChooserTests(TestCase):
    def test_coordinates_create_waze_and_google_maps_links(self):
        request = RequestFactory().get('/visitas/navegar/', {
            'lat': '-23.5416042', 'lng': '-46.9271697', 'nome': 'Madalena',
            'endereco': 'Avenida Carolina de Abreu Paulino, 3',
        })
        request.session = {}
        response = visitasNavegar(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Abrir no Waze')
        self.assertContains(response, 'Abrir no Google Maps')
        self.assertContains(response, 'll=-23.5416042%2C-46.9271697', html=False)
        self.assertContains(response, 'destination=-23.5416042%2C-46.9271697', html=False)

    def test_address_is_used_when_coordinates_are_missing(self):
        request = RequestFactory().get('/visitas/navegar/', {'endereco': 'Rua das Flores, 10'})
        request.session = {}
        response = visitasNavegar(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rua das Flores, 10')

    def test_missing_destination_returns_bad_request(self):
        request = RequestFactory().get('/visitas/navegar/')
        request.session = {}
        response = visitasNavegar(request)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Não foi possível identificar o destino', status_code=400)


class PrintedRoutePresentationTests(TestCase):
    def test_coordinate_prefix_is_hidden_from_printed_address(self):
        self.assertEqual(
            clean_visit_address('[-23.6203724, -46.9369216] Estrada Velha da Olaria, 1990'),
            'Estrada Velha da Olaria, 1990',
        )

    def test_route_is_ordered_by_scheduled_time(self):
        visits = [
            {'titulo': 'Segunda', 'data_inicio': '2026-08-14T09:45:00'},
            {'titulo': 'Quarta', 'data_inicio': '2026-08-14T09:15:00'},
            {'titulo': 'Terceira', 'data_inicio': '2026-08-14T09:30:00'},
            {'titulo': 'Primeira', 'data_inicio': '2026-08-14T09:00:00'},
        ]
        ordered = order_route_chronologically(visits)
        self.assertEqual([visit['titulo'] for visit in ordered], ['Primeira', 'Quarta', 'Terceira', 'Segunda'])

    def test_same_address_is_one_route_visit_without_linking_records(self):
        visits = [
            {
                'id': 'jorge-id', 'titulo': 'Jorge', 'data_inicio': '2026-08-15T09:00:00',
                'endereco_visitado': 'Rua Pivadávia, 70', 'apontamentos_restritos': '4 crianças',
            },
            {
                'id': 'renata-id', 'titulo': 'Renata', 'data_inicio': '2026-08-15T09:15:00',
                'endereco_visitado': '[-23.1, -46.2] Rua Pivadavia, 70', 'apontamentos_restritos': '4 crianças',
            },
        ]
        grouped = group_route_visits_by_address(visits)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]['titulo'], 'Jorge / Renata')
        self.assertEqual(grouped[0]['data_inicio'], '2026-08-15T09:00:00')
        self.assertEqual(grouped[0]['apontamentos_restritos'], '4 crianças')
        self.assertEqual(grouped[0]['endereco_visitado'], '[-23.1, -46.2] Rua Pivadavia, 70')
        self.assertEqual(visits[0]['titulo'], 'Jorge')
        self.assertEqual(visits[1]['titulo'], 'Renata')

    def test_missing_common_coordinates_does_not_create_fake_itapevi_distance(self):
        visits = [
            {
                'titulo': 'Jorge / Renata', 'data_inicio': '2026-08-15T09:00:00',
                'endereco_visitado': '[-23.6200000, -46.9360000] Rua Rivadávia, 70',
            },
            {
                'titulo': 'Maria', 'data_inicio': '2026-08-15T09:30:00',
                'endereco_visitado': '[-23.6203000, -46.9362000] Rua Rivadávia, 130',
            },
        ]
        ordered = order_route_chronologically(visits, start_coords=None)
        self.assertNotIn('distance_meters', ordered[0])
        self.assertLess(ordered[1]['distance_meters'], 100)

    def test_afternoon_continues_from_last_morning_house(self):
        route = [
            {'titulo': 'Manhã 1', 'data_inicio': '2026-08-15T09:00:00', 'endereco_visitado': '[-23.5000, -46.8990] Rua A, 1'},
            {'titulo': 'Manhã 2', 'data_inicio': '2026-08-15T09:15:00', 'endereco_visitado': '[-23.5000, -46.8980] Rua A, 2'},
            {'titulo': 'Tarde 1', 'data_inicio': '2026-08-15T14:00:00', 'endereco_visitado': '[-23.5000, -46.8970] Rua A, 3'},
        ]
        ordered = order_route_chronologically(route, start_coords=(-23.5000, -46.9000))
        self.assertLess(ordered[2]['distance_meters'], 150)
        self.assertGreater(ordered[2]['distance_meters'], 50)

    def test_visits_without_address_are_not_grouped(self):
        grouped = group_route_visits_by_address([
            {'titulo': 'Pessoa A', 'endereco_visitado': ''},
            {'titulo': 'Pessoa B', 'endereco_visitado': ''},
        ])
        self.assertEqual(len(grouped), 2)

    def test_route_address_key_counts_people_at_same_house_once(self):
        visits = [
            {'titulo': 'Pessoa A', 'endereco_visitado': '[-23.1, -46.2] Rua Um, 10'},
            {'titulo': 'Pessoa B', 'endereco_visitado': 'Rua Um, 10'},
            {'titulo': 'Pessoa C', 'endereco_visitado': 'Rua Um, 20'},
        ]
        keys = {route_address_key(visit) for visit in visits}
        self.assertEqual(len(keys), 2)

    @patch('ColorAdminApp.utils.routing.get_common_coordinates', return_value=(-23.5, -46.9))
    @patch('ColorAdminApp.utils.routing.requests.post')
    @patch('ColorAdminApp.utils.routing.requests.get')
    def test_auto_dispatch_fills_houses_and_combines_residents(self, get, post, _common):
        members = []
        for number in range(1, 13):
            members.append({
                'id': f'm-{number}', 'nome': f'Pessoa {number}', 'comum': 'COMUM A',
                'setor': 'Centro', 'status': 'Ativo',
                'endereco': f'[-23.5, -46.9] Rua Teste, {number}',
            })
        members.append({
            'id': 'm-1b', 'nome': 'Pessoa 1B', 'comum': 'COMUM A',
            'setor': 'Centro', 'status': 'Ativo',
            'endereco': '[-23.5, -46.9] Rua Teste, 1',
        })
        member_response = Mock(status_code=200)
        member_response.json.return_value = members
        agenda_response = Mock(status_code=200)
        agenda_response.json.return_value = []
        get.side_effect = [member_response, agenda_response]

        def created_response(*_args, **kwargs):
            response = Mock(status_code=201)
            response.json.return_value = [dict(item) for item in kwargs['json']]
            return response

        post.side_effect = created_response
        created = auto_dispatch_visits('Grupo A', '2026-08-15', comum='COMUM A')

        self.assertEqual(len(created), 10)
        self.assertEqual(len({route_address_key(visit) for visit in created}), 10)
        self.assertEqual(created[0]['titulo'], 'Pessoa 1 / Pessoa 1B')

    @patch('ColorAdminApp.utils.routing.get_common_coordinates', return_value=(-23.5, -46.9))
    @patch('ColorAdminApp.utils.routing.requests.post')
    @patch('ColorAdminApp.utils.routing.requests.get')
    def test_auto_dispatch_prioritizes_never_then_retry_then_oldest_visit(self, get, post, _common):
        members = [
            {'id': 'never', 'nome': 'Nunca', 'comum': 'COMUM A', 'setor': 'Centro', 'status': 'Ativo', 'endereco': '[-23.5, -46.9] Rua A, 1'},
            {'id': 'retry', 'nome': 'Retomar', 'comum': 'COMUM A', 'setor': 'Centro', 'status': 'Ativo', 'endereco': '[-23.5, -46.9] Rua A, 2'},
            {'id': 'old', 'nome': 'Antiga', 'comum': 'COMUM A', 'setor': 'Centro', 'status': 'Ativo', 'endereco': '[-23.5, -46.9] Rua A, 3'},
            {'id': 'recent', 'nome': 'Recente', 'comum': 'COMUM A', 'setor': 'Centro', 'status': 'Ativo', 'endereco': '[-23.5, -46.9] Rua A, 4'},
            {'id': 'frequent', 'nome': 'Mais visitada', 'comum': 'COMUM A', 'setor': 'Centro', 'status': 'Ativo', 'endereco': '[-23.5, -46.9] Rua A, 5'},
        ]
        history = [
            {'irmandade_id': 'retry', 'status': 'Não realizada', 'endereco_visitado': 'Rua A, 2', 'data_inicio': '2026-07-20T09:00:00-03:00'},
            {'irmandade_id': 'old', 'status': 'Realizada', 'endereco_visitado': 'Rua A, 3', 'data_inicio': '2026-01-10T09:00:00-03:00'},
            {'irmandade_id': 'recent', 'status': 'Realizada', 'endereco_visitado': 'Rua A, 4', 'data_inicio': '2026-08-10T09:00:00-03:00'},
            {'irmandade_id': 'frequent', 'status': 'Realizada', 'endereco_visitado': 'Rua A, 5', 'data_inicio': '2025-01-10T09:00:00-03:00'},
            {'irmandade_id': 'frequent', 'status': 'Realizada', 'endereco_visitado': 'Rua A, 5', 'data_inicio': '2025-02-10T09:00:00-03:00'},
        ]
        member_response = Mock(status_code=200)
        member_response.json.return_value = members
        agenda_response = Mock(status_code=200)
        agenda_response.json.return_value = history
        get.side_effect = [member_response, agenda_response]

        def created_response(*_args, **kwargs):
            response = Mock(status_code=201)
            response.json.return_value = [dict(item) for item in kwargs['json']]
            return response

        post.side_effect = created_response
        created = auto_dispatch_visits('Grupo A', '2026-08-15', comum='COMUM A')
        self.assertEqual(
            [visit['titulo'] for visit in created],
            ['Nunca', 'Retomar', 'Antiga', 'Recente', 'Mais visitada'],
        )


class RevokedSessionTests(TestCase):
    class Session(dict):
        def flush(self):
            self.clear()

    @patch("ColorAdminApp.middleware.requests.get")
    def test_deleted_user_is_logged_out_on_next_page(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = []
        request = RequestFactory().get("/visitas/dashboard/")
        request.session = self.Session(supabase_token="token", user_id="deleted-user")
        response = SupabaseAuthMiddleware(lambda _request: HttpResponse("protected"))(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/user/login-v1?reason=account_removed")
        self.assertEqual(request.session, {})

    @patch("ColorAdminApp.middleware.requests.get")
    def test_deleted_user_api_receives_unauthorized_response(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = []
        request = RequestFactory().get("/visitas/api/irmandade/")
        request.session = self.Session(supabase_token="token", user_id="deleted-user")
        response = SupabaseAuthMiddleware(lambda _request: HttpResponse("protected"))(request)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(json.loads(response.content)["code"], "account_removed")


class RegionalAccessTests(TestCase):
    def request_with_profile(self, profile):
        request = RequestFactory().get("/")
        request.session = {"user_profile": profile}
        return request

    @patch("ColorAdminApp.access_control.common_catalog", return_value=CATALOG)
    def test_local_user_only_sees_own_common(self, _catalog):
        scope = user_scope(self.request_with_profile({"role_id": 4, "comum": CATALOG[0]["comum"]}))
        self.assertTrue(can_access(scope, CATALOG[0]))
        self.assertFalse(can_access(scope, CATALOG[2]))

    @patch("ColorAdminApp.access_control.common_catalog", return_value=CATALOG)
    def test_municipal_coordinator_sees_only_municipality(self, _catalog):
        scope = user_scope(self.request_with_profile({"role_id": 3, "comum": CATALOG[0]["comum"]}))
        self.assertEqual(len(filter_rows(scope, CATALOG)), 2)
        self.assertFalse(can_access(scope, CATALOG[1]))

    @patch("ColorAdminApp.access_control.common_catalog", return_value=CATALOG)
    def test_regional_coordinator_sees_everything(self, _catalog):
        scope = user_scope(self.request_with_profile({"role_id": 2, "comum": CATALOG[0]["comum"]}))
        self.assertEqual(filter_rows(scope, CATALOG), CATALOG)

    @patch("ColorAdminApp.access_control.common_catalog", return_value=CATALOG)
    def test_global_level_has_full_scope(self, _catalog):
        scope = user_scope(self.request_with_profile({"role_id": 1, "comum": CATALOG[0]["comum"]}))
        self.assertEqual(scope["level"], "global")
        self.assertEqual(filter_rows(scope, CATALOG), CATALOG)

    @patch("ColorAdminApp.views.common_catalog", return_value=CATALOG)
    def test_registration_groups_searchable_commons_by_municipality(self, _catalog):
        request = RequestFactory().get("/user/cadastro")
        request.session = {}
        response = userRegisterV3(request)
        self.assertContains(response, '<optgroup label="ITAPEVI">')
        self.assertContains(response, '<optgroup label="JANDIRA">')
        self.assertContains(response, "$('#comum').select2")


class GlobalAdministrationTests(TestCase):
    def request_with_profile(self, role_id, path="/administracao/"):
        request = RequestFactory().get(path)
        request.session = {"user_profile": {"role_id": role_id}}
        return request

    def test_non_global_user_is_redirected_from_admin_page(self):
        response = administration(self.request_with_profile(2))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/v3")

    def test_non_global_user_is_forbidden_from_admin_api(self):
        response = administration_data(self.request_with_profile(3, "/administracao/api/dados/"))
        self.assertEqual(response.status_code, 403)

    @patch("ColorAdminApp.admin_views._get_table", return_value=[])
    def test_global_user_can_consult_admin_api(self, _get_table):
        response = administration_data(self.request_with_profile(1, "/administracao/api/dados/"))
        self.assertEqual(response.status_code, 200)

    @patch("ColorAdminApp.admin_views.log_audit")
    @patch("ColorAdminApp.admin_views.common_catalog", return_value=CATALOG)
    @patch("ColorAdminApp.admin_views.requests.patch")
    @patch("ColorAdminApp.admin_views._get_table")
    def test_local_approval_canonicalizes_common_and_municipality(self, get_table, patch_request, _catalog, _audit):
        get_table.return_value = [{"user_id": "user-1", "role_id": 4, "comum": CATALOG[0]["comum"]}]
        patch_request.return_value = Mock()
        patch_request.return_value.raise_for_status.return_value = None
        patch_request.return_value.json.return_value = [{"user_id": "user-1", "status": "approved"}]
        request = RequestFactory().patch(
            "/administracao/api/usuarios/user-1/",
            data={"status": "approved", "role_id": 4, "comum": CATALOG[0]["comum"]},
            content_type="application/json",
        )
        request.session = {"user_profile": {"role_id": 1}}
        response = administration_user(request, "user-1")
        self.assertEqual(response.status_code, 200)
        payload = patch_request.call_args.kwargs["json"]
        self.assertEqual(payload["comum"], CATALOG[0]["comum"])
        self.assertEqual(payload["municipio"], "ITAPEVI")
        self.assertEqual(payload["cidade"], "ITAPEVI")

    @patch("ColorAdminApp.admin_views.log_audit")
    @patch("ColorAdminApp.admin_views.requests.patch")
    @patch("ColorAdminApp.admin_views.requests.delete")
    @patch("ColorAdminApp.admin_views._get_table")
    def test_global_admin_deletes_auth_account_and_profile(self, get_table, delete_request, patch_request, audit):
        get_table.return_value = [{"user_id": "22222222-2222-2222-2222-222222222222", "full_name": "Teste"}]
        patch_request.return_value = Mock(status_code=204)
        delete_request.side_effect = [Mock(status_code=204), Mock(status_code=204)]
        request = RequestFactory().delete("/administracao/api/usuarios/22222222-2222-2222-2222-222222222222/")
        request.session = {"user_id": "11111111-1111-1111-1111-111111111111", "user_profile": {"role_id": 1}}
        response = administration_user(request, "22222222-2222-2222-2222-222222222222")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(patch_request.call_args.kwargs["json"], {"status": "rejected"})
        self.assertEqual(delete_request.call_count, 2)
        self.assertIn("/auth/v1/admin/users/", delete_request.call_args_list[0].args[0])
        self.assertIn("/rest/v1/profiles", delete_request.call_args_list[1].args[0])
        audit.assert_called_once()

    def test_global_admin_cannot_delete_own_active_account(self):
        user_id = "11111111-1111-1111-1111-111111111111"
        request = RequestFactory().delete(f"/administracao/api/usuarios/{user_id}/")
        request.session = {"user_id": user_id, "user_profile": {"role_id": 1, "user_id": user_id}}
        response = administration_user(request, user_id)
        self.assertEqual(response.status_code, 400)
        self.assertIn("própria conta", json.loads(response.content)["error"])


class LocalRegistrationFlowTests(TestCase):
    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.common_catalog", return_value=CATALOG)
    @patch("ColorAdminApp.views.requests.post")
    def test_registration_upserts_complete_local_profile(self, post, _catalog, _audit):
        auth_response = Mock(status_code=200, ok=True)
        auth_response.json.return_value = {"user": {"id": "user-local-1"}}
        profile_response = Mock(status_code=201, ok=True)
        profile_response.json.return_value = [{"user_id": "user-local-1"}]
        post.side_effect = [auth_response, profile_response]
        request = RequestFactory().post(
            "/api/auth/?action=register",
            data={
                "full_name": "Usuário Local", "email": "local@example.com",
                "password": "123456", "comum": CATALOG[0]["comum"],
            },
            content_type="application/json",
        )
        request.session = {}
        response = apiAuth(request)
        self.assertEqual(response.status_code, 200)
        profile = post.call_args_list[1].kwargs["json"]
        self.assertEqual(profile["user_id"], "user-local-1")
        self.assertEqual(profile["role_id"], 4)
        self.assertEqual(profile["status"], "pending")
        self.assertEqual(profile["comum"], CATALOG[0]["comum"])
        self.assertEqual(profile["municipio"], "ITAPEVI")

    @patch("ColorAdminApp.views.settings.SUPABASE_URL", "")
    @patch("ColorAdminApp.views.settings.SUPABASE_SERVICE_ROLE_KEY", "")
    def test_registration_reports_missing_supabase_configuration(self):
        request = RequestFactory().post(
            "/api/auth/?action=register",
            data={"full_name": "Teste", "email": "teste@example.com", "password": "123456", "comum": CATALOG[0]["comum"]},
            content_type="application/json",
        )
        request.session = {}
        response = apiAuth(request)
        self.assertEqual(response.status_code, 503)
        self.assertIn("não configurado", json.loads(response.content)["error"])

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.common_catalog", return_value=CATALOG)
    @patch("ColorAdminApp.views.requests.delete")
    @patch("ColorAdminApp.views.requests.post")
    def test_registration_rolls_back_auth_user_when_profile_save_fails(self, post, delete, _catalog, _audit):
        auth_response = Mock(status_code=200, ok=True)
        auth_response.json.return_value = {"user": {"id": "partial-user-1"}}
        profile_response = Mock(status_code=400, ok=False, text='{"message":"unknown column"}')
        post.side_effect = [auth_response, profile_response]
        delete.return_value = Mock(status_code=204, ok=True)
        request = RequestFactory().post(
            "/api/auth/?action=register",
            data={"full_name": "Teste", "email": "teste@example.com", "password": "123456", "comum": CATALOG[0]["comum"]},
            content_type="application/json",
        )
        request.session = {}
        response = apiAuth(request)
        self.assertEqual(response.status_code, 502)
        self.assertIn("Nenhuma conta foi mantida", json.loads(response.content)["error"])
        self.assertIn("/auth/v1/admin/users/partial-user-1", delete.call_args.args[0])


class IntelligentRouteTests(TestCase):
    def request(self, comum):
        request = RequestFactory().get("/visitas/api/roteiro-bairros/", {"comum": comum, "data": "2026-08-05"})
        request.session = {"user_profile": {"role_id": 4, "comum": comum}}
        return request

    @patch("ColorAdminApp.views.visible_commons", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}])
    @patch("ColorAdminApp.access_control.common_catalog", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}])
    @patch("ColorAdminApp.utils.routing.discover_nearby_neighborhoods", return_value=[{"nome": "Centro", "quantidade": 3, "distancia_metros": 450}])
    def test_neighborhoods_are_returned_for_common_in_scope(self, _discover, _catalog, _commons):
        response = apiRoteiroBairros(self.request("COMUM A"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Centro")

    @patch("ColorAdminApp.views.visible_commons", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}])
    @patch("ColorAdminApp.access_control.common_catalog", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}])
    def test_neighborhoods_reject_common_outside_scope(self, _catalog, _commons):
        response = apiRoteiroBairros(self.request("COMUM B"))
        self.assertEqual(response.status_code, 403)

    def test_route_finishes_neighborhood_before_starting_another(self):
        visits = [
            {"titulo": "Casa A 20", "setor": "Bairro A", "endereco_visitado": "[-23.5383, -46.9265] Rua Um, 20"},
            {"titulo": "Casa B", "setor": "Bairro B", "endereco_visitado": "[-23.6000, -47.0000] Rua Dois, 5"},
            {"titulo": "Casa A 10", "setor": "Bairro A", "endereco_visitado": "[-23.5384, -46.9266] Rua Um, 10"},
        ]
        route = optimize_route(visits)
        self.assertEqual([item["setor"] for item in route], ["Bairro A", "Bairro A", "Bairro B"])

    def test_same_street_stays_together_and_numbers_are_sequential(self):
        visits = [
            {"titulo": "N 30", "setor": "Centro", "endereco_visitado": "[-23.5403, -46.9265] Rua das Flores, 30"},
            {"titulo": "Outra", "setor": "Centro", "endereco_visitado": "[-23.5383, -46.9265] Rua Azul, 1"},
            {"titulo": "N 10", "setor": "Centro", "endereco_visitado": "[-23.5401, -46.9265] Rua das Flores, 10"},
            {"titulo": "N 20", "setor": "Centro", "endereco_visitado": "[-23.5402, -46.9265] Rua das Flores, 20"},
        ]
        route = optimize_route(visits)
        flower_positions = [index for index, item in enumerate(route) if street_key(item) == "RUA DAS FLORES"]
        self.assertEqual(flower_positions, list(range(min(flower_positions), max(flower_positions) + 1)))
        self.assertEqual(
            [route[index]["endereco_visitado"] for index in flower_positions],
            [
                "[-23.5401, -46.9265] Rua das Flores, 10",
                "[-23.5402, -46.9265] Rua das Flores, 20",
                "[-23.5403, -46.9265] Rua das Flores, 30",
            ],
        )

    def test_printed_route_keeps_every_scheduled_visit_above_reference(self):
        morning = [{"id": f"m-{index}"} for index in range(8)]
        afternoon = [{"id": f"t-{index}"} for index in range(8)]
        route = limit_daily_route(morning, afternoon)
        self.assertEqual(len(route), 16)
        self.assertEqual([item["id"] for item in route[:8]], [f"m-{index}" for index in range(8)])
        self.assertEqual([item["id"] for item in route[8:]], [f"t-{index}" for index in range(8)])

    def test_reference_does_not_remove_visits_from_either_shift(self):
        morning = [{"id": f"m-{index}"} for index in range(7)]
        afternoon = [{"id": f"t-{index}"} for index in range(3)]
        route = limit_daily_route(morning, afternoon)
        self.assertEqual(len(route), 10)
        self.assertEqual([item["id"] for item in route[:7]], [f"m-{index}" for index in range(7)])


class MapScopeFilterTests(TestCase):
    commons = [
        {"comum": "COMUM A", "cidade": "ITAPEVI"},
        {"comum": "COMUM B", "cidade": "ITAPEVI"},
        {"comum": "COMUM C", "cidade": "JANDIRA"},
    ]

    def map_request(self, role_id, comum="COMUM A", municipio="ITAPEVI"):
        request = RequestFactory().get("/visitas/mapa/")
        request.session = {"user_profile": {
            "role_id": role_id, "role": "USUARIO", "comum": comum, "municipio": municipio,
        }}
        return request

    @patch("ColorAdminApp.views.visible_commons", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}])
    def test_local_map_has_no_scope_selectors(self, _commons):
        response = visitasMapa(self.map_request(4))
        self.assertNotContains(response, 'id="map-municipio-filter"')
        self.assertNotContains(response, 'id="map-common-filter"')

    @patch("ColorAdminApp.views.visible_commons", return_value=commons[:2])
    def test_municipal_map_only_has_common_selector(self, _commons):
        response = visitasMapa(self.map_request(3))
        self.assertNotContains(response, 'id="map-municipio-filter"')
        self.assertContains(response, 'id="map-common-filter"')

    @patch("ColorAdminApp.views.visible_commons", return_value=commons)
    def test_regional_map_has_municipality_and_common_selectors(self, _commons):
        response = visitasMapa(self.map_request(2, comum="", municipio=""))
        self.assertContains(response, 'id="map-municipio-filter"')
        self.assertContains(response, 'id="map-common-filter"')

    @patch("ColorAdminApp.views.visible_commons", return_value=commons[:2])
    def test_members_api_rejects_common_outside_municipal_scope(self, _commons):
        request = RequestFactory().get("/visitas/api/irmandade/", {"comum": "COMUM C"})
        request.session = {"user_profile": {
            "role_id": 3, "role": "USUARIO", "comum": "COMUM A", "municipio": "ITAPEVI",
        }}
        response = apiVisitasIrmandade(request)
        self.assertEqual(response.status_code, 403)

    @patch("ColorAdminApp.views.visible_commons", return_value=commons)
    def test_regional_registration_has_municipality_and_searchable_common(self, _commons):
        response = visitasCadastro(self.map_request(2, comum="", municipio=""))
        self.assertContains(response, 'id="cadastro-municipio-filter"')
        self.assertContains(response, 'id="cadastro-common-filter"')
        self.assertContains(response, 'change.cadastroScope')

    @patch("ColorAdminApp.views.visible_commons", return_value=commons[:2])
    def test_municipal_registration_has_fixed_city_and_common_filter(self, _commons):
        response = visitasCadastro(self.map_request(3))
        self.assertNotContains(response, 'id="cadastro-municipio-filter"')
        self.assertContains(response, 'id="cadastro-common-filter"')

    @patch("ColorAdminApp.views.visible_commons", return_value=[commons[0]])
    def test_local_registration_uses_own_common_without_scope_filters(self, _commons):
        response = visitasCadastro(self.map_request(4))
        self.assertNotContains(response, 'id="cadastro-municipio-filter"')
        self.assertNotContains(response, 'id="cadastro-common-filter"')

    @patch("ColorAdminApp.views.visible_commons", return_value=commons)
    def test_regional_calendar_has_hierarchical_searchable_filters(self, _commons):
        response = visitasAgenda(self.map_request(2, comum="", municipio=""))
        self.assertContains(response, 'id="agenda-municipio-filter"')
        self.assertContains(response, 'id="agenda-comum-filter"')
        self.assertContains(response, "dayMaxEvents: 4")
        self.assertContains(response, "moreLinkClick: 'popover'")

    @patch("ColorAdminApp.views.visible_commons", return_value=[commons[0]])
    def test_local_calendar_uses_own_common_without_filters(self, _commons):
        response = visitasAgenda(self.map_request(4))
        self.assertNotContains(response, 'id="agenda-municipio-filter"')
        self.assertNotContains(response, 'id="agenda-comum-filter"')


class VisitTeamsTests(TestCase):
    def test_dashboard_date_filters_use_sao_paulo_exclusive_boundaries(self):
        request = RequestFactory().get('/visitas/dashboard/')
        request.session = {'user_profile': {
            'role_id': 1, 'role': 'ADMIN', 'cidade': '', 'municipio': '',
            'comum': '', 'nome': 'Administrador', 'email': 'admin@example.com',
        }}
        html = render_to_string('pages/visitas-dashboard.html', {
            'dashboard_access_level': 'global',
            'dashboard_comum_padrao': '',
            'dashboard_municipio_padrao': '',
            'dashboard_comuns': [],
            'dashboard_municipios': [],
        }, request=request)

        self.assertIn("const saoPauloDayStart = date => `${date}T00:00:00-03:00`;", html)
        self.assertIn("agendaParams.set('end_date', saoPauloNextDayStart(dataAte));", html)
        self.assertNotIn("`${dataAte}T23:59:59`", html)

    def test_legacy_team_names_are_normalized(self):
        self.assertEqual(normalize_visit_team("Equipe 01"), "Equipe 1")
        self.assertEqual(normalize_visit_team("Equipe de Visitas 02"), "Equipe 2")
        self.assertEqual(normalize_team_name("Grupo e", "regional"), "Grupo E")
        self.assertEqual(normalize_team_name("grupo a", "REGIONAL"), "Grupo A")

    @patch("ColorAdminApp.views.visible_commons", return_value=CATALOG)
    @patch("ColorAdminApp.views.requests.get")
    def test_monthly_dashboard_uses_recorded_city_and_gvmu_musicians(self, get, _commons):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [
            {"comum": "LEGACY ITAPEVI", "municipio": "ITAPEVI", "gvi": 238, "gvm": 142, "gvmu": 23, "rf": 280, "re": 74},
            {"comum": "BR-02 - JARDIM JANDIRA", "municipio": "JANDIRA", "gvi": 215, "gvm": 60, "gvmu": 24, "rf": 126, "re": 64},
        ]
        request = RequestFactory().get('/visitas/api/dashboard/', {"ano": "2026", "mes": "7", "municipio": "ITAPEVI"})
        request.session = {"user_profile": {"role_id": 1}}

        response = apiVisitas(request)
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["municipio"], "ITAPEVI")
        self.assertEqual(payload[0]["gve"], 23)

    @patch("ColorAdminApp.views.visible_commons", return_value=CATALOG)
    @patch("ColorAdminApp.views.requests.get")
    def test_unfiltered_agenda_hydrates_common_from_member(self, get, _commons):
        agenda_response = Mock(status_code=200)
        agenda_response.json.return_value = [{
            "id": "visit-1", "irmandade_id": "member-1", "comum": None,
            "data_inicio": "2026-08-01T09:00:00-03:00", "categoria": "GVI",
        }]
        members_response = Mock(status_code=200)
        members_response.json.return_value = [{"id": "member-1", "comum": "BR-01 - CENTRAL ITAPEVI"}]
        get.side_effect = [agenda_response, members_response]
        request = RequestFactory().get('/visitas/api/agenda/', {
            "start_date": "2026-01-01T00:00:00", "end_date": "2027-01-01T00:00:00",
        })
        request.session = {"user_profile": {"role_id": 1}}

        response = apiVisitasAgenda(request)
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload[0]["comum"], "BR-01 - CENTRAL ITAPEVI")
        self.assertEqual(payload[0]["municipio"], "ITAPEVI")

    def test_report_names_use_consistent_capitalization(self):
        self.assertEqual(format_display_name("ADERBAL BAZANTE"), "Aderbal Bazante")
        self.assertEqual(format_display_name("IAIR JOÃO"), "Iair João")
        self.assertEqual(format_display_name("ADERBAL, ABNER, REINALDO E HENRIQUE"), "Aderbal, Abner, Reinaldo e Henrique")
        self.assertEqual(format_display_name("GRUPO RF"), "Grupo RF")

    @patch("ColorAdminApp.views.visible_commons", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}])
    def test_local_team_report_locks_city_and_common(self, _commons):
        request = RequestFactory().get('/visitas/relatorios-equipes/')
        request.session = {"user_profile": {"role_id": 4, "role": "USUARIO", "comum": "COMUM A", "municipio": "ITAPEVI"}}
        response = visitasRelatoriosEquipes(request)
        self.assertContains(response, 'id="report-city" class="form-select" disabled')
        self.assertContains(response, 'id="report-common" class="form-select" disabled')
        self.assertContains(response, 'id="report-podium"')
        self.assertContains(response, 'id="ranking-chart"')
        self.assertContains(response, 'id="status-chart"')
        self.assertContains(response, 'id="trend-chart"')

    @patch("ColorAdminApp.views.visible_commons", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}, {"comum": "COMUM B", "cidade": "ITAPEVI"}])
    def test_municipal_team_report_locks_city_but_allows_common_search(self, _commons):
        request = RequestFactory().get('/visitas/relatorios-equipes/')
        request.session = {"user_profile": {"role_id": 3, "role": "USUARIO", "comum": "COMUM A", "municipio": "ITAPEVI"}}
        response = visitasRelatoriosEquipes(request)
        self.assertContains(response, 'id="report-city" class="form-select" disabled')
        self.assertContains(response, 'id="report-common" class="form-select" >')

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.post")
    def test_regional_group_is_created_by_city(self, post, _audit):
        post.return_value = Mock(status_code=201)
        post.return_value.json.return_value = [{"id": "group-a", "nome": "Grupo A"}]
        request = RequestFactory().post(
            "/visitas/api/equipes/",
            data={"acao": "cadastrar_equipe", "tipo": "REGIONAL", "municipio": "ITAPEVI", "nome": "grupo a"},
            content_type="application/json",
        )
        request.session = {"user_id": "user-1", "user_profile": {"role_id": 1}}

        response = apiVisitasEquipes(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.call_args.kwargs["json"], {
            "nome": "Grupo A", "tipo": "REGIONAL", "municipio": "ITAPEVI", "comum": None, "ativo": True,
        })

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.delete")
    @patch("ColorAdminApp.views.requests.patch")
    @patch("ColorAdminApp.views.requests.get")
    def test_deleting_team_detaches_members_and_preserves_registrations(self, get, patch_request, delete, _audit):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [{
            "id": "team-1", "nome": "Equipe 1", "tipo": "LOCAL",
            "municipio": "ITAPEVI", "comum": "COMUM A",
        }]
        patch_request.return_value = Mock(status_code=200)
        delete.return_value = Mock(status_code=204)
        request = RequestFactory().delete("/visitas/api/equipes/?equipe_id=team-1")
        request.session = {"user_id": "user-1", "user_profile": {"role_id": 1}}

        response = apiVisitasEquipes(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(patch_request.call_args.kwargs["json"], {"equipe_id": None, "equipe_visita": None})
        self.assertEqual(delete.call_args.kwargs["params"], {"id": "eq.team-1"})

    @patch("ColorAdminApp.views.visible_commons", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}])
    @patch("ColorAdminApp.views.requests.get")
    def test_members_mode_includes_people_without_team(self, get, _commons):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [{
            "id": "1", "nome": "Rodrigo", "comum": "COMUM A",
            "status": "Ativo", "equipe_visita": None, "cargo_outros": "",
        }]
        request = RequestFactory().get("/visitas/api/equipes/?modo=membros&elegiveis=true&comum=COMUM A")
        request.session = {"user_profile": {"role_id": 4, "comum": "COMUM A", "municipio": "ITAPEVI"}}
        response = apiVisitasEquipes(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rodrigo")

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.patch")
    @patch("ColorAdminApp.views.requests.get")
    @patch("ColorAdminApp.views.visible_commons", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}])
    def test_existing_member_is_assigned_to_team(self, _commons, get, patch_request, _audit):
        member_response = Mock(status_code=200)
        member_response.json.return_value = [{"id": "1", "nome": "Ricardo", "comum": "COMUM A", "cidade": "ITAPEVI", "cargo_outros": "Grupo de Visitas"}]
        team_response = Mock(status_code=200)
        team_response.json.return_value = [{"id": "team-1", "nome": "Equipe 1", "tipo": "LOCAL", "municipio": "ITAPEVI", "comum": "COMUM A"}]
        get.side_effect = [member_response, team_response]
        patch_request.return_value = Mock(status_code=200)
        patch_request.return_value.json.return_value = [{"id": "1", "equipe_visita": "Equipe 1"}]
        request = RequestFactory().post(
            "/visitas/api/equipes/",
            data={"membro_id": "1", "equipe_id": "team-1", "equipe": "Equipe 01"},
            content_type="application/json",
        )
        request.session = {"user_id": "user-1", "user_profile": {"role_id": 1, "comum": "COMUM A", "municipio": "ITAPEVI"}}
        response = apiVisitasEquipes(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(patch_request.call_args.kwargs["json"], {
            "equipe_id": "team-1", "equipe_visita": "Equipe 1", "cargo_outros": "Grupo de Visitas",
        })

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.patch")
    @patch("ColorAdminApp.views.requests.get")
    @patch("ColorAdminApp.views.visible_commons", return_value=[{"comum": "COMUM A", "cidade": "ITAPEVI"}])
    def test_regional_assignment_does_not_replace_local_team(self, _commons, get, patch_request, _audit):
        member_response = Mock(status_code=200)
        member_response.json.return_value = [{
            "id": "1", "nome": "Ricardo", "comum": "COMUM A", "cargo_outros": "Grupo de Visitas",
            "equipe_id": "local-1", "equipe_visita": "Equipe 1",
        }]
        team_response = Mock(status_code=200)
        team_response.json.return_value = [{
            "id": "regional-a", "nome": "Grupo A", "tipo": "REGIONAL", "municipio": "ITAPEVI", "comum": None,
        }]
        get.side_effect = [member_response, team_response]
        patch_request.return_value = Mock(status_code=200)
        patch_request.return_value.json.return_value = [{"id": "1", "grupo_regional_nome": "Grupo A"}]
        request = RequestFactory().post(
            "/visitas/api/equipes/",
            data={"membro_id": "1", "equipe_id": "regional-a", "equipe": "Grupo A"},
            content_type="application/json",
        )
        request.session = {"user_id": "user-1", "user_profile": {"role_id": 1, "comum": "COMUM A", "municipio": "ITAPEVI"}}

        response = apiVisitasEquipes(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(patch_request.call_args.kwargs["json"], {
            "grupo_regional_id": "regional-a", "grupo_regional_nome": "Grupo A", "cargo_outros": "Grupo de Visitas",
        })

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.patch")
    @patch("ColorAdminApp.views.requests.get")
    def test_legacy_and_current_names_do_not_conflict(self, get, patch_request, _audit):
        current = Mock(status_code=200)
        current.json.return_value = [{
            "id": "visit-1", "data_inicio": "2026-08-01T09:00:00-03:00",
            "setor": "Centro", "equipe_responsavel": "Equipe 01", "status": "Marcada",
        }]
        same_day = Mock(status_code=200)
        same_day.json.return_value = [{
            "id": "visit-2", "setor": "Centro",
            "equipe_responsavel": "Equipe de Visitas 01", "status": "Marcada",
        }]
        get.side_effect = [current, same_day]
        patch_request.return_value = Mock(status_code=200, text='[{"id":"visit-1"}]')
        patch_request.return_value.json.return_value = [{"id": "visit-1"}]
        request = RequestFactory().patch(
            "/visitas/api/agenda/?id=visit-1",
            data={"equipe_responsavel": "Equipe 1"}, content_type="application/json",
        )
        request.session = {"user_id": "user-1", "user_profile": {"role_id": 1}}

        response = apiVisitasAgenda(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(patch_request.call_args.kwargs["json"]["equipe_responsavel"], "Equipe 1")

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.post")
    @patch("ColorAdminApp.views.requests.get")
    def test_retroactive_completed_visit_ignores_territorial_reservation(self, get, post, _audit):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = []
        post.return_value = Mock(status_code=201, text='[{"id":"visit-retroactive"}]')
        post.return_value.json.return_value = [{"id": "visit-retroactive"}]
        request = RequestFactory().post(
            "/visitas/api/agenda/",
            data={
                "irmandade_id": "member-1",
                "data_inicio": "2026-08-01T10:30:00-03:00",
                "status": "Realizada",
                "setor": "Vila Aurora",
                "equipe_responsavel": "Equipe 1",
            },
            content_type="application/json",
        )
        request.session = {"user_id": "user-1", "user_profile": {"role_id": 1}}

        response = apiVisitasAgenda(request)

        self.assertEqual(response.status_code, 200)
        get.assert_called_once()
        post.assert_called_once()

    @patch("ColorAdminApp.views.requests.post")
    @patch("ColorAdminApp.views.requests.get")
    def test_duplicate_retroactive_visit_is_rejected(self, get, post):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [{"id": "existing-visit", "status": "Realizada"}]
        request = RequestFactory().post(
            "/visitas/api/agenda/",
            data={
                "irmandade_id": "member-robson",
                "data_inicio": "2026-08-01T10:30:00-03:00",
                "status": "Realizada",
                "setor": "Vila Aurora",
                "equipe_responsavel": "Equipe 1",
            },
            content_type="application/json",
        )
        request.session = {"user_id": "user-1", "user_profile": {"role_id": 1}}

        response = apiVisitasAgenda(request)

        self.assertEqual(response.status_code, 409)
        self.assertIn("já possui uma visita", json.loads(response.content)["error"])
        post.assert_not_called()

    @patch("ColorAdminApp.views.requests.post")
    @patch("ColorAdminApp.views.requests.get")
    def test_visit_without_responsible_team_is_rejected(self, get, post):
        request = RequestFactory().post(
            "/visitas/api/agenda/",
            data={
                "irmandade_id": "member-claudia",
                "data_inicio": "2026-08-15T14:00:00-03:00",
                "status": "Realizada",
                "categoria": "GVI",
                "equipe_responsavel": "",
            },
            content_type="application/json",
        )
        request.session = {"user_id": "user-1", "user_profile": {"role_id": 1}}

        response = apiVisitasAgenda(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("equipe responsável", json.loads(response.content)["error"])
        get.assert_not_called()
        post.assert_not_called()


class BrotherhoodUpdateTests(TestCase):
    @patch("ColorAdminApp.views.requests.get")
    def test_members_are_ordered_ignoring_whitespace_and_accents(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [
            {"id": "4", "nome": " Wellington", "comum": "COMUM A"},
            {"id": "3", "nome": "Áurelia", "comum": "COMUM A"},
            {"id": "2", "nome": "  Acacio", "comum": "COMUM A"},
            {"id": "1", "nome": "Abner", "comum": "COMUM A"},
        ]
        request = RequestFactory().get("/visitas/api/irmandade/")
        request.session = {"user_profile": {"role_id": 1}}

        response = apiVisitasIrmandade(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["nome"].strip() for row in json.loads(response.content)],
            ["Abner", "Acacio", "Áurelia", "Wellington"],
        )

    @patch("ColorAdminApp.views.requests.get")
    def test_restricted_notes_are_removed_from_instructor_response(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [{
            "id": "member-1", "nome": "Criança", "comum": "COMUM A", "cidade": "ITAPEVI",
            "apontamentos_restritos": "Visita somente com coordenador",
        }]
        request = RequestFactory().get("/visitas/api/irmandade/")
        request.session = {"user_profile": {"role_id": 4, "comum": "COMUM A", "municipio": "ITAPEVI"}}

        response = apiVisitasIrmandade(request)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("apontamentos_restritos", json.loads(response.content)[0])

    @patch("ColorAdminApp.views.requests.get")
    def test_restricted_notes_are_returned_to_coordinator(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [{
            "id": "member-1", "nome": "Criança", "comum": "COMUM A", "cidade": "ITAPEVI",
            "apontamentos_restritos": "Visita somente com coordenador",
        }]
        request = RequestFactory().get("/visitas/api/irmandade/")
        request.session = {"user_profile": {"role_id": 3, "municipio": "ITAPEVI"}}

        response = apiVisitasIrmandade(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)[0]["apontamentos_restritos"], "Visita somente com coordenador")

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.post")
    @patch("ColorAdminApp.views.requests.get")
    def test_smart_import_preserves_existing_and_deduplicates_file(self, get, post, _audit):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [{"nome": "José da Silva", "comum": "COMUM A"}]
        post.return_value = Mock(status_code=201)
        post.return_value.json.return_value = [{"id": "new-1"}]
        payload = [
            {"nome": "Jose da Silva", "comum": "COMUM A"},
            {"nome": "Ana Souza", "comum": "COMUM A"},
            {"nome": "  ANA   SOUZA ", "comum": "COMUM A"},
        ]
        request = RequestFactory().post("/visitas/api/irmandade/?smart=1", data=payload, content_type="application/json")
        request.session = {"user_profile": {"role_id": 1}}
        response = apiVisitasIrmandade(request)
        result = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(result, {"created": 1, "updated": 0, "skipped": 2, "smart_import": True})
        self.assertEqual(len(post.call_args.kwargs["json"]), 1)
        self.assertEqual(post.call_args.kwargs["json"][0]["nome"], "Ana Souza")

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.patch")
    @patch("ColorAdminApp.views.requests.post")
    @patch("ColorAdminApp.views.requests.get")
    def test_smart_import_enriches_existing_visit_period(self, get, post, patch_request, _audit):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [{
            "id": "member-1", "nome": "Maria", "comum": "VILA DAS CHACARAS",
            "preferencia_periodo_visita": None, "classificacao_adicional": "Avivamento",
        }]
        patch_request.return_value = Mock(status_code=204, text="")
        payload = [{
            "nome": "Maria", "comum": "VILA DAS CHACARAS",
            "preferencia_periodo_visita": "Manhã", "classificacao_adicional": "Avivamento",
        }]
        request = RequestFactory().post("/visitas/api/irmandade/?smart=1", data=payload, content_type="application/json")
        request.session = {"user_profile": {"role_id": 1}}

        response = apiVisitasIrmandade(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"created": 0, "updated": 1, "skipped": 0, "smart_import": True})
        patch_request.assert_called_once()
        self.assertEqual(patch_request.call_args.kwargs["json"], {"preferencia_periodo_visita": "Manhã"})
        post.assert_not_called()

    @patch("ColorAdminApp.views.requests.get")
    def test_export_reads_all_supabase_pages(self, get):
        first = Mock(status_code=206)
        first.json.return_value = [{"id": str(index), "nome": f"Membro {index}", "comum": "COMUM A"} for index in range(1000)]
        second = Mock(status_code=200)
        second.json.return_value = [{"id": "1000", "nome": "Membro 1000", "comum": "COMUM A"}]
        get.side_effect = [first, second]
        request = RequestFactory().get("/visitas/api/irmandade/?export=1")
        request.session = {"user_profile": {"role_id": 1}}
        response = apiVisitasIrmandade(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(json.loads(response.content)), 1001)
        self.assertEqual(get.call_count, 2)

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.post")
    def test_bulk_import_accepts_a_valid_batch(self, post, _audit):
        post.return_value = Mock(status_code=201)
        post.return_value.json.return_value = [{"id": "1"}, {"id": "2"}]
        payload = [
            {"nome": "Maria", "comum": "COMUM A", "cargo_outros": "Organista", "id_chefe_familia": ""},
            {"nome": "João", "comum": "COMUM B", "cargo_outros": "Músico"},
        ]
        request = RequestFactory().post("/visitas/api/irmandade/", data=payload, content_type="application/json")
        request.session = {"user_profile": {"role_id": 1}}
        response = apiVisitasIrmandade(request)
        self.assertEqual(response.status_code, 200)
        sent = post.call_args.kwargs["json"]
        self.assertIsNone(sent[0]["id_chefe_familia"])
        self.assertIsNone(sent[1]["id_chefe_familia"])
        self.assertEqual(set(sent[0]), set(sent[1]))

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.patch")
    @patch("ColorAdminApp.views.requests.get")
    def test_patch_defines_endpoint_before_reading_current_record(self, get, patch_request, _audit):
        current = {"id": "member-1", "nome": "Maria", "comum": "COMUM A", "cidade": "ITAPEVI"}
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [current]
        patch_request.return_value = Mock(status_code=200, text='')
        request = RequestFactory().patch(
            "/visitas/api/irmandade/?id=member-1",
            data={"nome": "Maria Atualizada"}, content_type="application/json",
        )
        request.session = {"user_profile": {"role_id": 4, "comum": "COMUM A", "municipio": "ITAPEVI"}}
        response = apiVisitasIrmandade(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("/rest/v1/visitas_irmandade", get.call_args.args[0])

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.patch")
    @patch("ColorAdminApp.views.requests.get")
    def test_instructor_cannot_write_restricted_notes_directly(self, get, patch_request, _audit):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = [{"id": "member-1", "nome": "Maria", "comum": "COMUM A", "cidade": "ITAPEVI"}]
        patch_request.return_value = Mock(status_code=204, text="")
        request = RequestFactory().patch(
            "/visitas/api/irmandade/?id=member-1",
            data={"nome": "Maria", "apontamentos_restritos": "Dado indevido"}, content_type="application/json",
        )
        request.session = {"user_profile": {"role_id": 4, "comum": "COMUM A", "municipio": "ITAPEVI"}}

        response = apiVisitasIrmandade(request)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("apontamentos_restritos", patch_request.call_args.kwargs["json"])

    @patch("ColorAdminApp.views.log_audit")
    @patch("ColorAdminApp.views.requests.patch")
    @patch("ColorAdminApp.views.requests.get")
    def test_mutual_spouse_link_keeps_existing_family_head(self, get, patch_request, _audit):
        current_response = Mock(status_code=200)
        current_response.json.return_value = [{"id": "ricardo", "nome": "Ricardo", "comum": "COMUM A"}]
        spouse_response = Mock(status_code=200)
        spouse_response.json.return_value = [{"id": "vanessa", "id_chefe_familia": "ricardo", "vinculo_tipo": "Cônjuge"}]
        get.side_effect = [current_response, spouse_response]
        patch_request.return_value = Mock(status_code=200, text='')
        request = RequestFactory().patch(
            "/visitas/api/irmandade/?id=ricardo",
            data={"id_chefe_familia": "vanessa", "vinculo_tipo": "Cônjuge"},
            content_type="application/json",
        )
        request.session = {"user_profile": {"role_id": 1}}

        response = apiVisitasIrmandade(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(patch_request.call_args.kwargs["json"]["id_chefe_familia"])
        self.assertIsNone(patch_request.call_args.kwargs["json"]["vinculo_tipo"])
