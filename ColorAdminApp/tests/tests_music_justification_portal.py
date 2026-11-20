import json
import io
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import Mock, patch
from contextlib import ExitStack

import requests
from django.core import signing
from django.core.cache import cache
from django.test import Client, RequestFactory, SimpleTestCase, override_settings

from ColorAdminApp.modules import music_justification_portal as portal
from ColorAdminApp.modules.music_events_conductors import summarize
from ColorAdminApp.modules import music_justification_reports as reports


class PortalDomainTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.row = {'id': 'j1', 'agenda_id': 'a'*24, 'evento_titulo': 'Ensaio regional Cotia',
            'tipo': 'ENSAIO_REGIONAL', 'familia': 'GERAL', 'data_evento': '2026-11-15', 'hora': '09:00',
            'municipios': ['COTIA'], 'municipio': 'COTIA', 'local': '', 'comum_codigo': 'BR-22-1',
            'comum': 'BR-22-1 - Central', 'person_key': 'irmandade:1', 'nome': 'José Silva',
            'motivo': 'Compromisso de trabalho', 'created_at': '2026-11-14T15:00:00Z', 'roles': ['ENCARREGADO_LOCAL']}
        self.event = {'id': 'e1', 'tipo': 'ENSAIO_REGIONAL', 'familia': 'GERAL',
                      'data_evento': '2026-11-15', 'titulo': 'Ensaio regional', 'status': 'ABERTO'}
        self.site = {'id': 's1', 'evento_id': 'e1', 'nome': 'Central Cotia', 'municipio': 'COTIA'}

    def test_real_agenda_event_titles(self):
        cases = [('Ensaio por Família – Cordas (Cotia)', ('REUNIAO_TECNICA', 'CORDAS')),
                 ('Ensaio Técnico - Família Cordas (Jandira)', ('REUNIAO_TECNICA', 'CORDAS')),
                 ('Ensaio Técnico - Família Metais - Fazendinha (Santana de Parnaíba)', ('REUNIAO_TECNICA', 'METAIS')),
                 ('Ensaio por Família (Metais) Granja Alvorada (Jandira)', ('REUNIAO_TECNICA', 'METAIS')),
                 ('Reunião Técnica Madeiras', ('REUNIAO_TECNICA', 'MADEIRAS')),
                 ('Reunião de Encarregados Locais (Cotia)', ('REUNIAO_MINISTERIO', 'GERAL')),
                 ('Reunião Musical Geral (Jandira)', ('REUNIAO_MINISTERIO', 'GERAL')),
                 ('Reunião Geral da Música (Itapevi)', ('REUNIAO_MINISTERIO', 'GERAL')),
                 ('Ensaio Local (Itapevi)', (None, None)), ('Exame de Músicos', (None, None))]
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(portal.classify(title), expected)
        self.assertEqual(portal.title_cities('Ensaio Regional – Central (Vargem Grande)'), ['VARGEM GRANDE PAULISTA'])
        self.assertEqual(portal.title_cities('Reunião Musical (Fazendinha)'), ['SANTANA DE PARNAÍBA'])
        self.assertEqual(portal.agenda_location('Ensaio Regional – Vila Monte Serrat/Central (Cotia)'), 'Vila Monte Serrat/Central')
        self.assertEqual(portal.agenda_location('Ensaio por Família (Metais) Granja Alvorada (Jandira)'), 'Granja Alvorada')
        self.assertEqual(portal.agenda_location('Reunião Musical (Cotia)'), '')

    def test_only_global_can_delete_and_tampered_selection_cannot_write(self):
        request = RequestFactory().post('/musica/justificativas/api/painel/', data=json.dumps({'action': 'delete', 'token': 'forged'}), content_type='application/json')
        request.session = {'user_id': 'actor', 'user_profile': {'nome': 'Administrador'}}
        with patch.object(portal.events, '_allowed', return_value=True), patch.object(portal.requests, 'post') as write:
            for level in ['municipal', 'regional']:
                with patch.object(portal, 'user_scope', return_value={'level': level}):
                    self.assertEqual(portal.dashboard_api(request).status_code, 403)
            with patch.object(portal, 'user_scope', return_value={'level': 'global'}):
                self.assertEqual(portal.dashboard_api(request).status_code, 400)
            write.assert_not_called()

    def test_global_deletes_public_and_ministry_copies_with_exact_filters(self):
        refs = [{'source': 'public', 'id': 'public-id', 'year': '2026'},
                {'source': 'ministry', 'event': 'event-id', 'person': 'sam:123', 'year': '2026'}]
        token = signing.dumps(refs, salt='music-justification-delete')
        request = RequestFactory().post('/musica/justificativas/api/painel/', data=json.dumps({'action': 'delete', 'token': token}), content_type='application/json')
        request.session = {'user_id': 'actor', 'user_profile': {'nome': 'Administrador'}}
        with patch.object(portal.events, '_allowed', return_value=True), patch.object(portal, 'user_scope', return_value={'level': 'global'}), \
             patch.object(portal.requests, 'post', return_value=Mock(status_code=200, json=lambda: {'deleted': True})) as write, \
             patch.object(portal.events, '_invalidate_annual') as invalidate, patch('ColorAdminApp.views.log_audit') as audit:
            self.assertEqual(portal.dashboard_api(request).status_code, 200)
            self.assertEqual(write.call_count, 2)
            self.assertEqual(write.call_args_list[0].kwargs['json']['p_id'], 'public-id')
            self.assertEqual(write.call_args_list[1].kwargs['json']['p_event'], 'event-id')
            self.assertEqual(write.call_args_list[1].kwargs['json']['p_person'], 'sam:123')
            self.assertEqual(invalidate.call_count, 2)
            audit.assert_called_once()

    def test_missing_delete_migration_returns_specific_message(self):
        token = signing.dumps([{'source': 'public', 'id': 'public-id', 'year': '2026'}], salt='music-justification-delete')
        request = RequestFactory().post('/', data=json.dumps({'action': 'delete', 'token': token}), content_type='application/json')
        request.session = {'user_id': 'actor', 'user_profile': {'nome': 'Administrador'}}
        with patch.object(portal.events, '_allowed', return_value=True), patch.object(portal, 'user_scope', return_value={'level': 'global'}), \
             patch.object(portal.requests, 'post', return_value=Mock(status_code=404)):
            response = portal.dashboard_api(request)
        self.assertEqual(response.status_code, 503)
        self.assertIn('063_musica_justificativas_exclusao.sql', json.loads(response.content)['error'])

    def test_global_legacy_deletion_reuses_individual_group_handler(self):
        refs = [{'source': 'legacy', 'event': 'event-id', 'id': 'group-id:1', 'year': '2026'}]
        request = RequestFactory().post('/', data=json.dumps({'action':'delete','token': signing.dumps(refs, salt='music-justification-delete')}), content_type='application/json')
        request.session = {'user_id': 'actor', 'user_profile': {'nome': 'Administrador'}}
        from django.http import JsonResponse
        with patch.object(portal.events, '_allowed', return_value=True), patch.object(portal, 'user_scope', return_value={'level': 'global'}), \
             patch('ColorAdminApp.modules.music_events_justifications.manage_grouped', return_value=JsonResponse({'alterados': 1})) as grouped, \
             patch.object(portal.events, '_invalidate_annual'), patch('ColorAdminApp.views.log_audit'):
            self.assertEqual(portal.dashboard_api(request).status_code, 200)
            self.assertEqual(grouped.call_args.args[2:], ('excluir', 'actor', {'ids': ['group-id:1']}))

    def test_event_window_limits_two_open_and_one_preview_and_rotates(self):
        rows = [{'id': str(i), 'data_evento': f'2026-11-{20+i}', 'titulo': 'Ensaio',
                 'hora': '16:00', 'municipios': ['JANDIRA']} for i in range(5)]
        with patch.object(portal, 'today', return_value='2026-11-20'):
            result = portal.event_window(list(reversed(rows)), 'JANDIRA')
        self.assertEqual([r['id'] for r in result], ['0', '1', '2'])
        self.assertEqual([r['aberto'] for r in result], [True, True, False])
        with patch.object(portal, 'today', return_value='2026-11-21'):
            result = portal.event_window(rows, 'JANDIRA')
        self.assertEqual([r['id'] for r in result], ['1', '2', '3'])
        self.assertEqual([r['aberto'] for r in result], [True, True, False])

    def test_agenda_meeting_is_created_once_without_attendance(self):
        event = {'id': 'a'*24, 'titulo': 'Reunião Geral da Música (Itapevi)',
                 'tipo': 'REUNIAO_MINISTERIO', 'familia': 'GERAL', 'data_evento': '2026-11-28',
                 'municipios': ['ITAPEVI'], 'local': 'Itapevi'}
        row = {**event, 'municipio': 'ITAPEVI'}
        own = []
        with patch('ColorAdminApp.modules.music_ministry._rpc', return_value={'id': 'meeting'}) as rpc:
            first = portal.ensure_agenda_meeting(event, row, [], own, [])
            second = portal.ensure_agenda_meeting(event, row, [], own, [])
        self.assertEqual(first, second)
        rpc.assert_called_once()
        payload = rpc.call_args.args[1]['p_evento']
        self.assertEqual(payload['registros'], [])
        self.assertFalse(payload['lista_completa'])
        self.assertIsNone(rpc.call_args.args[1]['p_hash'])

    def test_technical_agenda_creates_event_and_site_without_attendance(self):
        event = {'id': 'b'*24, 'titulo': 'Ensaio Técnico - Família Metais - Fazendinha (Santana de Parnaíba)',
                 'tipo': 'REUNIAO_TECNICA', 'familia': 'METAIS', 'data_evento': '2026-11-21',
                 'municipios': ['SANTANA DE PARNAÍBA'], 'local': 'Fazendinha', 'hora': '19:30'}
        row = {**event, 'municipio': 'SANTANA DE PARNAÍBA'}
        saved = {**event, 'id': 'created', 'status': 'RASCUNHO'}
        legacy, sites = [], []
        with patch.object(portal.events, '_read', side_effect=[[], [saved]]), \
             patch.object(portal.requests, 'post', return_value=Mock()) as post, \
             patch.object(portal.requests, 'patch', return_value=Mock()) as update, \
             patch.object(portal.events, '_invalidate_annual'):
            target = portal.ensure_agenda_meeting(event, row, legacy, [], sites)
        self.assertEqual(target, saved)
        self.assertEqual(post.call_count, 2)
        self.assertIsNone(post.call_args_list[0].kwargs['json']['base_id'])
        self.assertEqual(post.call_args_list[0].kwargs['json']['familia'], 'METAIS')
        self.assertEqual(post.call_args_list[1].kwargs['json']['nome'], 'Fazendinha')
        update.assert_not_called()
        self.assertEqual(portal.agenda_location(event['titulo']), 'Fazendinha')
        self.assertEqual(portal.agenda_location('Ensaio Técnico - Família Cordas (Jandira)'), '')

    def test_existing_submission_is_linked_to_official_agenda_automatically(self):
        event = {'id': 'a'*24, 'titulo': 'Reunião Geral da Música (Itapevi)',
                 'tipo': 'REUNIAO_MINISTERIO', 'familia': 'GERAL', 'data_evento': '2026-11-28',
                 'municipios': ['ITAPEVI'], 'local': 'Itapevi'}
        row = {**self.row, 'agenda_id': event['id'], 'tipo': event['tipo'],
               'data_evento': event['data_evento'], 'municipio': 'ITAPEVI', 'municipios': event['municipios']}
        with patch.object(portal, 'submissions', return_value=[row]), patch.object(portal, 'agenda', return_value=[event]), \
             patch.object(portal, 'projection_context', return_value=([], [], [])), \
             patch.object(portal, 'ensure_agenda_meeting', return_value={'id': 'meeting'}), \
             patch.object(portal.requests, 'patch', return_value=Mock()) as write, \
             patch.object(portal.events, '_invalidate_annual'):
            self.assertEqual(portal.sync_agenda_links(), 1)
        self.assertEqual(write.call_args.kwargs['json']['ministerio_evento_id'], 'meeting')
        self.assertEqual(write.call_args.kwargs['params']['ministerio_evento_id'], 'is.null')

    def test_specific_secretary_role_replaces_generic_role(self):
        roles = ['SECRETARIO_A_MUSICA', 'SECRETARIO_MUSICA', 'SECRETARIO_MUSICA']
        self.assertEqual(portal.role_label(roles), 'Secretário da Música')
        result = portal.with_roles([{**self.row, 'roles': roles}])[0]
        self.assertEqual(result['roles'], ['SECRETARIO_MUSICA'])
        self.assertEqual(result['cargo'], 'Secretário da Música')
        self.assertEqual(portal.role_label(['SECRETARIO_A_MUSICA', 'SECRETARIA_MUSICA']), 'Secretária da Música')

    def test_search_reuses_prepared_directory_and_submission_refreshes_identity(self):
        person = {'key': 'sam:1', 'nome': 'José Silva', 'comum': self.row['comum'], 'roles': ['INSTRUTOR']}
        with patch.object(portal, 'registered_people', side_effect=[[person], []]) as directory:
            first = portal.people()
            second = portal.people()
            self.assertEqual(directory.call_count, 1)
            self.assertEqual(first, second)
            self.assertEqual(first[0]['_common_code'], 'BR-22-1')
            self.assertEqual(first[0]['_search_name'], 'JOSE SILVA')
            self.assertEqual(portal.people(fresh=True), [])
            self.assertEqual(directory.call_count, 2)

    def test_search_api_does_not_write_navigation_audit_for_logged_in_visitors(self):
        from django.http import JsonResponse
        from ColorAdminApp.middleware import SupabaseAuthMiddleware
        middleware = SupabaseAuthMiddleware(lambda request: JsonResponse({'people': []}))
        for path in ['/justificativas/api/', '/justificativas-musicais/api/']:
            request = RequestFactory().get(path)
            request.session = {'user_id': 'visitor', 'audit_access_session_id': 'access-session'}
            with patch('ColorAdminApp.views.log_audit') as audit, patch('ColorAdminApp.middleware.requests.patch') as activity:
                self.assertEqual(middleware(request).status_code, 200)
            audit.assert_not_called()
            activity.assert_not_called()
        request = RequestFactory().get('/justificativas/')
        request.session = {'user_id': 'visitor', 'audit_access_session_id': 'access-session'}
        with patch('ColorAdminApp.views.log_audit') as audit, patch('ColorAdminApp.middleware.requests.patch') as activity:
            middleware(request)
        audit.assert_called_once()
        activity.assert_called_once()

    def test_csv_classification_future_filter_and_regional_coverage(self):
        csv = ('DATA,HORA,EVENTO,DEPARTAMENTO\n'
               '15/11/2026,09:00,Ensaio Regional – Central (Cotia),Música\n'
               '28/11/2026,09:00,Reunião Musical (Regional - Itapevi),Música\n'
               '28/11/2026,10:00,Reunião Musical (Local desconhecido),Música\n'
               '28/11/2026,10:00,Reunião Musical (Cotia),Ministério\n'
               '30/02/2026,09:00,Ensaio Regional (Cotia),Música\n')
        with patch.object(portal.requests, 'get', return_value=Mock(content=csv.encode())):
            rows = portal.agenda()
        self.assertEqual(len(rows), 3)
        regional = next(r for r in rows if 'Regional - Itapevi' in r['titulo'])
        self.assertEqual(set(regional['municipios']), set(portal.REGIONAL))
        unknown = next(r for r in rows if 'desconhecido' in r['titulo'])
        self.assertEqual(unknown['municipios'], [])

    def test_unique_match_checks_date_kind_family_and_destination(self):
        self.assertEqual(portal.resolve_target(self.row, [self.event], [], [self.site]), self.event)
        for change in [{'data_evento': '2026-11-16'}, {'tipo': 'REUNIAO_TECNICA'}, {'familia': 'CORDAS'}]:
            self.assertIsNone(portal.resolve_target(self.row, [{**self.event, **change}], [], [self.site]))
        self.assertIsNone(portal.resolve_target(self.row, [self.event], [], [{**self.site, 'municipio': 'ITAPEVI'}]))

    def test_ambiguous_matches_are_not_assigned_and_explicit_binding_is_respected(self):
        other = {**self.event, 'id': 'e2'}
        sites = [self.site, {**self.site, 'evento_id': 'e2'}]
        self.assertIsNone(portal.resolve_target(self.row, [self.event, other], [], sites))
        self.assertEqual(portal.resolve_target({**self.row, 'evento_id': 'e2'}, [self.event, other], [], sites), other)
        self.assertIsNone(portal.resolve_target({**self.row, 'evento_id': 'deleted'}, [self.event], [], sites))

    def test_ministry_municipality_is_required(self):
        row = {**self.row, 'tipo': 'REUNIAO_MINISTERIO'}
        event = {**self.event, 'tipo': 'REUNIAO_MINISTERIO', 'municipios': ['ITAPEVI']}
        self.assertIsNone(portal.resolve_target(row, [], [event], []))
        event['municipios'] = ['COTIA']
        self.assertEqual(portal.resolve_target(row, [], [event], []), event)

    def test_city_and_venue_must_belong_to_the_same_site(self):
        row = {**self.row, 'local': 'Vila Monte Serrat'}
        sites = [{**self.site, 'nome': 'Outro bairro'},
                 {**self.site, 'id': 's2', 'nome': 'Vila Monte Serrat', 'municipio': 'JANDIRA'}]
        self.assertIsNone(portal.resolve_target(row, [self.event], [], sites))

    def test_changing_bound_event_date_does_not_move_justification(self):
        changed = {**self.event, 'data_evento': '2026-12-15'}
        self.assertIsNone(portal.resolve_target({**self.row, 'evento_id': 'e1'}, [changed], [], [self.site]))

    def test_projection_uses_full_candidate_pool_not_selected_event_only(self):
        other = {**self.event, 'id': 'e2'}
        with patch.object(portal, 'submissions', return_value=[self.row]), patch.object(portal, 'projection_context',
                return_value=([self.event, other], [], [self.site, {**self.site, 'evento_id': 'e2'}])):
            self.assertEqual(portal.public_reviews([self.event]), [])

    def test_non_local_cargos_do_not_inflate_local_conductor_conferences(self):
        rows = [{**self.row, 'id': 'secretary', 'roles': ['SECRETARIO_MUSICA']},
                {**self.row, 'id': 'regional', 'roles': ['ENCARREGADO_REGIONAL']},
                {**self.row, 'id': 'teacher', 'roles': ['INSTRUTORA']}, self.row]
        with patch.object(portal, 'submissions', return_value=rows), patch.object(portal, 'projection_context',
                return_value=([self.event], [], [self.site])):
            result = portal.public_reviews([self.event])
            legacy, own = portal.ministry_projection([self.event], [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], self.row['id'])
        self.assertEqual(len(legacy), 4)
        self.assertEqual(legacy[0]['roles'], ['SECRETARIO_MUSICA'])
        self.assertEqual(own, [])

    def test_role_spelling_gender_and_generic_sam_secretariat(self):
        from ColorAdminApp.modules.music_ministry_domain import roles_of
        examples = {'Encarregado Local': ['ENCARREGADO_LOCAL'], 'Encarregado Regional': ['ENCARREGADO_REGIONAL'],
                    'Examinadora de Organistas': ['EXAMINADORA'], 'Secretário da Música': ['SECRETARIO_MUSICA'],
                    'Secretária da Música': ['SECRETARIA_MUSICA'], 'Secretário do GEM': ['SECRETARIO_GEM'],
                    'Secretária do GEM': ['SECRETARIA_GEM'], 'SECRETÁRIO (A) DA MÚSICA': ['SECRETARIO_A_MUSICA'],
                    'Instrutor': ['INSTRUTOR'], 'Instrutora': ['INSTRUTORA']}
        for value, expected in examples.items():
            with self.subTest(cargo=value):
                self.assertEqual(roles_of(value), expected)

    def test_registered_person_key_recovers_dated_role_without_assuming_local_conductor(self):
        row = {k: v for k, v in self.row.items() if k != 'roles'}
        row.update(person_key='sam:1', data_evento='2026-10-15')
        person = {'key': 'sam:1', 'aliases': ['sam:1'], 'roles': ['SECRETARIO_MUSICA']}
        current = {'id': '1', 'cargo_ministerio': 'Secretário da Música'}
        change = {'id': 'c1', 'aluno_id': '1', 'campo': 'cargo_ministerio', 'anterior': 'Instrutor',
                  'posterior': 'Secretário da Música', 'effective_at': '2026-11-01T00:00:00-03:00', 'date_basis': 'manual'}
        with patch.object(portal, 'registered_people', return_value=[person]), patch.object(portal, 'member_directory', return_value=[]), \
             patch.object(portal.events, '_registry', return_value=[current]), patch.object(portal.events, '_transitions', return_value=[change]):
            before = portal.with_roles([row])[0]
            after = portal.with_roles([{**row, 'data_evento': '2026-11-15'}])[0]
            unknown = portal.with_roles([{**row, 'person_key': 'sam:missing'}])[0]
        self.assertEqual(before['roles'], ['INSTRUTOR'])
        self.assertEqual(after['roles'], ['SECRETARIO_MUSICA'])
        self.assertEqual(unknown['roles'], [])
        self.assertEqual(unknown['cargo'], 'Cargo a Conferir')

    def test_auxiliary_membership_cargo_is_preserved_and_sam_identity_deduplicated(self):
        from ColorAdminApp.modules.music_ministry_domain import roster
        catalog = [{'comum': self.row['comum'], 'cidade': 'COTIA'}]
        sam = [{'id': 'sam1', 'nome_aluno': 'José Silva', 'comum_congregacao': self.row['comum'],
                'municipio': 'COTIA', 'cargo_ministerio': 'SECRETÁRIO (A) DA MÚSICA', 'status': 'CONCLUIDO'}]
        members = [{'id': 'member1', 'nome': 'José Silva', 'comum': self.row['comum'], 'cidade': 'COTIA',
                    'cargo_outros': 'Secretário da Música,Grupo de Visitas', 'status': 'ATIVO'}]
        result = roster(sam, members, catalog)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['roles'], ['SECRETARIO_MUSICA'])
        self.assertEqual(set(result[0]['aliases']), {'sam:sam1', 'irmandade:member1'})
        sam[0]['cargo_ministerio'] = 'Músico'
        result = roster(sam, members, catalog)
        self.assertEqual(result[0]['roles'], ['SECRETARIO_MUSICA'])
        sam[0]['status'] = 'INATIVO'
        self.assertEqual(roster(sam, members, catalog), [])

    def test_justification_counts_per_conductor_and_does_not_add_nominal_presence(self):
        with patch.object(portal, 'submissions', return_value=[self.row]), patch.object(portal, 'projection_context',
                return_value=([self.event], [], [self.site])):
            reviews = portal.public_reviews([self.event])
        catalog = [{'comum': self.row['comum'], 'cidade': 'COTIA'}]
        registry = [{'id': '1', 'nome_aluno': 'José Silva', 'comum_congregacao': self.row['comum'],
                     'municipio': 'COTIA', 'cargo_ministerio': 'Encarregado Local', 'status': 'ATIVO'}]
        result = summarize([self.event], [], [self.site], reviews, {'origem': 'regional'}, catalog, leaders=registry)
        classified = [r for r in result['rows'] if r.get('encarregado_nome') == 'José Silva']
        self.assertEqual(len(classified), 1)
        self.assertEqual(classified[0]['situacao'], 'JUSTIFICOU')
        self.assertFalse(classified[0]['consta_lista'])

    def test_alias_merge_preserves_presence_and_deduplicates_justification(self):
        person = {'key': 'irmandade:1', 'aliases': ['irmandade:1', 'sam:7'], 'nome': 'José Silva', 'comum': self.row['comum']}
        old = {'event_id': 'e1', 'person_key': 'sam:7', 'situacao': 'PRESENTE', 'nome': 'José Silva', 'comum': self.row['comum']}
        new = {**old, 'person_key': 'irmandade:1', 'situacao': 'JUSTIFICOU'}
        self.assertEqual(portal.merge_ministry_entries([old], [new], [person]), [old])
        merged = portal.merge_ministry_entries([{**old, 'situacao': 'SEM_REGISTRO'}], [new], [person])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['situacao'], 'JUSTIFICOU')

    def test_missing_migration_keeps_existing_panels_readable(self):
        response = Mock(status_code=404)
        with patch.object(portal.events, '_read', side_effect=requests.HTTPError(response=response)):
            self.assertEqual(portal.submissions(), [])
        response.status_code = 503
        with patch.object(portal.events, '_read', side_effect=requests.HTTPError(response=response)):
            with self.assertRaises(requests.HTTPError):
                portal.submissions()

    def test_historical_sources_use_latest_import_and_expand_individual_justifications(self):
        from ColorAdminApp.modules.music_events_justifications import pack_metadata
        old = {**self.event, 'created_at': '2026-11-16T10:00:00Z'}
        current = {**old, 'id': 'e2', 'created_at': '2026-11-17T10:00:00Z'}
        review = {'id': 'r1', 'evento_id': 'e1', 'situacao': 'JUSTIFICOU', 'comum_chave': 'BR-22-1',
                  'comum_nome': self.row['comum'], 'municipio': 'COTIA', 'created_at': self.row['created_at'],
                  'observacoes': pack_metadata({'nome': 'Cadastro antigo', 'motivo': 'Trabalho'})}
        current_review = {**review, 'id': 'r2', 'evento_id': 'e2', 'observacoes': pack_metadata({'pessoas': [
            {'nome': 'Primeiro encarregado', 'motivo': 'Trabalho'}, {'nome': 'Segundo encarregado', 'motivo': 'Viagem'}]})}
        def read(table, **kwargs):
            return {'musica_eventos': [old,current], 'musica_ministerio_eventos': [],
                    'musica_evento_encarregados': [review,current_review], 'musica_evento_locais': []}[table]
        with patch.object(portal.events, '_read', side_effect=read):
            rows, legacy, own, sites = portal.historical_sources()
        self.assertEqual(len(rows), 2)
        self.assertEqual({r['event_key'] for r in rows}, {'legado:e2'})
        self.assertEqual({r['nome'] for r in rows}, {'Primeiro encarregado', 'Segundo encarregado'})
        self.assertTrue(all(r['destino'] == 'e2' for r in rows))

    def test_dashboard_combines_sources_without_double_counting_and_lists_upcoming_agenda(self):
        historical = {**self.row, 'destino': 'e1', 'event_key': 'legado:e1', 'candidates': []}
        meeting = {'id': 'meeting', 'titulo': 'Reunião Geral da Música (Itapevi)', 'data_evento': '2026-11-28',
                   'tipo': 'REUNIAO_MINISTERIO', 'familia': 'GERAL', 'municipios': sorted(portal.REGIONAL), 'local': 'Itapevi'}
        request = RequestFactory().get('/musica/justificativas/api/painel/', {'evento': 'legado:e1'})
        with patch.object(portal, 'historical_sources', return_value=([historical], [self.event], [], [self.site])), \
             patch.object(portal, 'submissions', return_value=[self.row]), \
             patch.object(portal, 'catalog', return_value=[{'comum': self.row['comum'], 'cidade': 'COTIA'}]), \
             patch.object(portal, 'agenda', return_value=[meeting]), patch.object(portal, 'today', return_value='2026-11-20'), \
             patch.object(portal, 'user_scope', return_value={'level': 'global'}):
            result = portal.dashboard_data(request)
        self.assertEqual(result['metrics']['total'], 1)
        self.assertEqual(result['metrics']['ENSAIO_REGIONAL'], 1)
        self.assertEqual(result['metrics']['pendentes'], 0)
        self.assertTrue(any(e['id'] == 'agenda:meeting' for e in result['options']['events']))
        self.assertEqual(sum(g['total'] for g in result['groups']), 1)


@override_settings(SUPABASE_URL='https://db.example', SUPABASE_SERVICE_ROLE_KEY='test')
class PortalApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.common = {'comum': 'BR-22-1 - Central', 'cidade': 'COTIA'}
        self.person = {'key': 'sam:1', 'nome': 'José Silva', 'comum': self.common['comum'], 'roles': ['ENCARREGADO_LOCAL']}
        self.event = {'id': 'a'*24, 'titulo': 'Ensaio regional (Cotia)', 'data_evento': '2026-11-15',
                      'hora': '09:00', 'tipo': 'ENSAIO_REGIONAL', 'familia': 'GERAL', 'local': '', 'municipios': ['COTIA']}
        self.token = signing.dumps({'key': 'sam:1', 'nome': 'José Silva', 'comum': 'BR-22-1'}, salt=portal.SALT)
        self.payload = {'evento': 'a'*24, 'comum': 'BR-22-1', 'pessoa': self.token, 'motivo': 'Trabalho'}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in [('agenda', [self.event]), ('catalog', [self.common]), ('people', [self.person]),
                            ('today', '2026-11-15'), ('projection_context', ([], [], [])),
                            ('historical_sources', ([], [], [], []))]:
            self.stack.enter_context(patch.object(portal, name, return_value=value))
        self.post = self.stack.enter_context(patch.object(portal.requests, 'post', return_value=Mock(status_code=201)))

    def send(self, **changes):
        request = self.factory.post('/justificativas/api/', data=json.dumps({**self.payload, **changes}), content_type='application/json')
        return portal.public_api(request)

    def test_submission_uses_server_identity_and_snapshot(self):
        self.assertEqual(self.send(nome='Nome forjado', tipo='REUNIAO_MINISTERIO').status_code, 201)
        saved = self.post.call_args.kwargs['json']
        self.assertEqual(saved['nome'], 'José Silva')
        self.assertEqual(saved['tipo'], 'ENSAIO_REGIONAL')
        self.assertEqual(saved['person_key'], 'sam:1')
        self.assertEqual(saved['comum_codigo'], 'BR-22-1')
        self.assertEqual(saved['motivo'], 'Trabalho')
        self.assertEqual(self.send(motivo='Outros').status_code,400)
        self.assertEqual(self.send(motivo='Outros',detalhe='x'*493).status_code,400)
        self.assertEqual(self.send(motivo='Outros',detalhe='Compromisso familiar').status_code,201)
        self.assertEqual(self.post.call_args.kwargs['json']['motivo'],'Outros: Compromisso familiar')

    def test_requested_music_cargos_can_submit_with_their_registered_identity(self):
        for role in portal.PUBLIC_ROLES:
            with self.subTest(cargo=role):
                person = {**self.person, 'roles': [role], 'cargo': portal.ROLES[role]}
                with patch.object(portal, 'people', return_value=[person]):
                    self.assertEqual(self.send(roles=['ENCARREGADO_LOCAL']).status_code, 201)
                    self.assertEqual(self.post.call_args.kwargs['json']['person_key'], 'sam:1')
                    self.assertNotIn('roles', self.post.call_args.kwargs['json'])

    def test_past_event_rejected_before_writing(self):
        with patch.object(portal, 'today', return_value='2026-11-16'):
            self.assertEqual(self.send().status_code, 409)
        self.post.assert_not_called()

    def test_wrong_common_inactive_person_unknown_event_and_tampered_token_rejected(self):
        for change in [{'comum': 'BR-22-2'}, {'evento': 'b'*24}, {'pessoa': self.token + 'bad'}, {'motivo': 'abc'}, {'motivo': 'x'*501}]:
            with self.subTest(change=change):
                self.assertIn(self.send(**change).status_code, [400, 409])
        with patch.object(portal, 'people', return_value=[]):
            self.assertEqual(self.send().status_code, 400)
        self.post.assert_not_called()

    def test_municipality_checked_on_server(self):
        self.event['municipios'] = ['ITAPEVI']
        self.assertEqual(self.send().status_code, 400)
        self.post.assert_not_called()

    def test_search_partial_terms_stays_in_selected_common(self):
        person = {**self.person, 'nome': 'Ricardo de Castro Grangeiro'}
        outsider = {**person, 'key': 'sam:2', 'comum': 'BR-22-2 - Vila'}
        with patch.object(portal, 'people', return_value=[person, outsider]):
            result = portal.public_api(self.factory.get('/', {'comum': 'BR-22-1', 'q': 'Ricardo G'}))
        rows = json.loads(result.content)['people']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['codigo'], 'BR-22-1')

    def test_local_event_rejects_outside_scope_and_manual_registration(self):
        self.assertEqual(self.send(evento_municipio='ITAPEVI').status_code, 400)
        self.assertEqual(self.send(manual={'nome':'Visitante da Musica','cargo':'SECRETARIO_MUSICA'}).status_code, 400)
        outsider = {**self.person, 'comum': 'BR-22-2 - Vila'}
        with patch.object(portal, 'people', return_value=[outsider]):
            self.assertEqual(self.send().status_code, 400)
        self.post.assert_not_called()

    def test_regional_event_accepts_member_of_each_covered_municipality(self):
        self.event['municipios'] = list(portal.REGIONAL)
        for city in portal.REGIONAL:
            common = {**self.common, 'cidade': city}
            with patch.object(portal, 'catalog', return_value=[common]):
                self.assertEqual(self.send(evento_municipio=city).status_code, 201)
                self.assertEqual(self.post.call_args.kwargs['json']['municipio'], city)

    def test_duplicate_and_midnight_database_rejection(self):
        self.post.return_value.status_code = 409
        self.assertEqual(self.send().status_code, 409)
        self.post.return_value.status_code = 400
        self.post.return_value.text = 'Prazo de justificativas encerrado.'
        self.assertEqual(self.send().status_code, 409)

    def test_public_search_minimum_length_and_no_reason_exposure(self):
        result = portal.public_api(self.factory.get('/justificativas/api/', {'comum': 'BR-22-1', 'q': 'J'}))
        self.assertEqual(json.loads(result.content), {'people': []})
        result = portal.public_api(self.factory.get('/justificativas/api/', {'comum': 'BR-22-1', 'q': 'José'}))
        item = json.loads(result.content)['people'][0]
        self.assertEqual(set(item), {'nome', 'cargo', 'token', 'codigo', 'comum', 'municipio'})
        self.assertEqual(item['cargo'], 'Encarregado Local')

    def test_dashboard_requires_authorization_and_checks_scope_before_metrics(self):
        request = self.factory.get('/musica/justificativas/api/painel/')
        with patch.object(portal.events, '_allowed', return_value=False):
            self.assertEqual(portal.dashboard_api(request).status_code, 403)
        scope = {'level': 'municipal', 'municipio': 'COTIA'}
        row = {'comum': self.common['comum'], 'municipio': 'ITAPEVI'}
        with patch.object(portal.events, '_allowed', return_value=True), patch.object(portal, 'user_scope', return_value=scope), patch.object(portal, 'submissions', return_value=[row]), patch.object(portal, 'can_access', return_value=False):
            data = json.loads(portal.dashboard_api(request).content)
        self.assertEqual(data['metrics']['total'], 0)
        self.assertEqual(data['options']['cities'], [])
        self.assertFalse(data['can_manage'])

    def test_music_access_does_not_depend_on_gem_access(self):
        request = self.factory.get('/musica/justificativas/')
        request.session = {'authenticated': True}
        with patch.object(portal.events, 'can_access_module', return_value=True) as access:
            self.assertTrue(portal.events._allowed(request))
        access.assert_called_once_with(request, 'musica')

    def test_restricted_profile_cannot_bind_even_with_guessed_ids(self):
        request = self.factory.post('/musica/justificativas/api/painel/',data=json.dumps({'id':'guessed','destino':'guessed'}),content_type='application/json')
        with patch.object(portal.events,'_allowed',return_value=True), patch.object(portal,'user_scope',return_value={'level':'municipal'}), patch.object(portal.requests,'patch') as write:
            self.assertEqual(portal.dashboard_api(request).status_code,403)
        write.assert_not_called()

    @override_settings(MIDDLEWARE=['django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.csrf.CsrfViewMiddleware'], SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies')
    def test_public_route_renders_and_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        page = client.get('/justificativas/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Justificativa de Ausência')
        self.assertContains(page, 'ram-event-select')
        legacy = client.get('/justificativas-musicais/?origem=link')
        self.assertEqual(legacy.status_code, 301)
        self.assertEqual(legacy['Location'], '/justificativas/?origem=link')
        response = client.post('/justificativas/api/', data=json.dumps(self.payload), content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.post.assert_not_called()


class JustificationReportTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026,11,20,10,30,tzinfo=ZoneInfo('America/Sao_Paulo'))
        self.row = {'evento_titulo':'Ensaio regional Cotia','data_evento':'2026-11-15','hora':'09:00',
                    'familia':'GERAL','municipio':'COTIA','comum':'BR-22-1 - CENTRAL','nome':'Pessoa de teste',
                    'motivo':'Compromisso de trabalho','created_at':'2026-11-14T15:20:00Z','destino':'e1'}
        self.data = {'items':[self.row],'metrics':{'pendentes':0},'options':{'events':[]}}

    def test_pdf_institutional_identity_dates_and_page_width(self):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(reports.build_pdf(self.data,{'municipio':'COTIA'},'Operador de teste',self.now)))
        text = reader.pages[0].extract_text()
        for expected in ['CONGREGAÇÃO CRISTÃ NO BRASIL','Regional Itapevi - São Paulo','Responsável:',
                         'Secretaria Regional da Música','Impresso por:','Operador de teste','20/11/2026 10:30',
                         '15/11/2026','14/11/2026 12:20','Compromisso de trabalho','Contabilização']:
            self.assertIn(expected,text)
        self.assertNotIn('2026-11-15',text)
        self.assertGreater(float(reader.pages[0].mediabox.width),float(reader.pages[0].mediabox.height))

    def test_excel_template_print_layout_literal_values_and_full_reasons(self):
        from openpyxl import load_workbook
        data = {**self.data,'items':[{**self.row,'motivo':'=DANGER() ' + 'Motivo detalhado. '*25}]}
        book = load_workbook(io.BytesIO(reports.build_excel(data,{},'Operador de teste',self.now)))
        sheet = book.active
        self.assertEqual(sheet['A1'].value,'CONGREGAÇÃO CRISTÃ NO BRASIL')
        self.assertEqual(sheet['A7'].fill.fgColor.rgb,'001E4B7A')
        self.assertEqual(sheet['D8'].data_type,'s')
        self.assertEqual(sheet['D8'].value,data['items'][0]['motivo'])
        self.assertGreater(sheet.row_dimensions[8].height,100)
        self.assertFalse(sheet.sheet_view.showGridLines)
        self.assertEqual(sheet.freeze_panes,'A8')
        self.assertEqual(sheet.auto_filter.ref,'A7:F8')
        self.assertEqual(sheet.page_setup.fitToWidth,1)
        self.assertEqual(sheet.print_title_rows,'$1:$7')
        self.assertIn('Secretaria Regional da Música',str(sheet['A5'].value))
        self.assertIn('Operador de teste',sheet.oddFooter.right.text)

    def test_export_requires_permission_and_reuses_dashboard_filters(self):
        request = RequestFactory().get('/musica/justificativas/exportar-pdf/',{'municipio':'COTIA','tipo':'ENSAIO_REGIONAL'})
        request.session = {'user_profile':{'full_name':'Operador de teste'}}
        with patch.object(portal.events,'_allowed',return_value=False):
            self.assertEqual(reports.export(request,'pdf').status_code,403)
        with patch.object(portal.events,'_allowed',return_value=True), patch.object(portal,'dashboard_data',return_value=self.data) as dashboard:
            response = reports.export(request,'pdf')
        dashboard.assert_called_once_with(request)
        self.assertEqual(response['Content-Type'],'application/pdf')
        self.assertIn("filename*=UTF-8''",response['Content-Disposition'])
        self.assertIn('JUSTIFICATIVAS',response['Content-Disposition'])
