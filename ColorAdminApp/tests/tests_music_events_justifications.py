import io
import json
from contextlib import ExitStack
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, RequestFactory
from openpyxl import Workbook

from ColorAdminApp.modules import music_events_justifications as module


class JustificationImportTests(SimpleTestCase):
    def test_reason_column_omits_names_and_deduplicates_equal_reasons(self):
        notes = module.pack_metadata({'nome': 'JORGE / OTONIEL',
            'motivo': 'JORGE: Enfermidade | OTONIEL: Enfermidade',
            'pessoas': [{'nome': 'JORGE', 'motivo': 'Enfermidade'},
                        {'nome': 'OTONIEL', 'motivo': 'Enfermidade'}]})
        self.assertEqual(module.reason_summary(notes), 'Enfermidade')
        self.assertEqual(module.display_note(notes), 'JORGE: Enfermidade | OTONIEL: Enfermidade')
        different = module.pack_metadata({'pessoas': [{'nome': 'A', 'motivo': 'Trabalho'},
                                                     {'nome': 'B', 'motivo': 'Questão familiar'}]})
        self.assertEqual(module.reason_summary(different), 'Trabalho | Questão familiar')
        self.assertEqual(module.reason_summary('Outro motivo'), 'Outro motivo')

    def test_two_people_in_legacy_common_record_keep_independent_names_and_reasons(self):
        event = {'id': 'e'}
        notes = module.pack_metadata({'nome': 'JORGE AMÂNCIO / OTONIEL LUIZ',
            'motivo': 'Motivos individuais', 'pessoas': [
                {'nome': 'JORGE AMÂNCIO', 'motivo': 'Idade avançada', 'situacao': 'JUSTIFICOU'},
                {'nome': 'OTONIEL LUIZ', 'motivo': 'Questão familiar', 'situacao': 'JUSTIFICOU'}]})
        original = {'id': 'original', 'evento_id': 'e', 'comum_chave': 'BR-22-1252',
                    'comum_nome': 'BR-22-1252 - JARDIM ISAURA', 'municipio': 'SANTANA DE PARNAÍBA',
                    'situacao': 'JUSTIFICOU', 'observacoes': notes}
        with patch.object(module.events, '_read', return_value=[original]):
            rows, available = module.events._reviews([event])
        self.assertTrue(available)
        self.assertEqual([(row['encarregado_nome'], row['observacoes']) for row in rows],
                         [('JORGE AMÂNCIO', 'Idade avançada'), ('OTONIEL LUIZ', 'Questão familiar')])
        self.assertTrue(all(row['id'] == 'original' for row in rows))
        self.assertEqual(original['observacoes'], notes)

    def setUp(self):
        self.catalog = [{'comum': 'BR-22-1 - JARDIM COTIA', 'cidade': 'COTIA'}]
        self.leaders = [{'nome_aluno': 'Natanael Zanin', 'cargo_ministerio': 'Encarregado Local',
                         'comum_congregacao': 'BR-22-1 - JARDIM COTIA', 'municipio': 'COTIA', 'status': 'ATIVO'}]
        self.row = {'nome': 'Natanael Zanin', 'comum': 'Jardim Cotia', 'cargo': 'Encarregado Local', 'motivo': 'Viagem'}

    def test_only_identified_leaders_and_deduplication(self):
        rows = [self.row, self.row, {**self.row, 'cargo': 'Músico'}, {**self.row, 'nome': 'Outra pessoa'},
                {**self.row, 'comum': 'Não identificada'}]
        result = module.reconcile(rows, self.catalog, self.leaders, '2026-11-15')
        self.assertEqual(len(result), 4)
        self.assertFalse(result[0]['problema'])
        self.assertEqual(result[0]['municipio'], 'COTIA')
        self.assertTrue(all(r['problema'] for r in result[1:]))

    def test_wrong_date_and_ambiguous_common_are_pending(self):
        result = module.reconcile([{**self.row, 'data_evento': '20/09/2026'}], self.catalog, self.leaders, '2026-11-15')
        self.assertIn('Data', result[0]['problema'])
        catalog = self.catalog + [{'comum': 'BR-22-2 - JARDIM COTIA', 'cidade': 'ITAPEVI'}]
        unmatched = {**self.row, 'nome': 'Pessoa não cadastrada'}
        self.assertTrue(module.reconcile([unmatched], catalog, self.leaders, '2026-11-15')[0]['problema'])

    def test_jardim_primavera_code_resolves_across_cotia_and_caucaia_names(self):
        catalog = [{'comum': 'BR-22-3376 - JARDIM PRIMAVERA - COTIA', 'cidade': 'CAUCAIA DO ALTO'}]
        leaders = [{'nome_aluno': 'Amarildo Pereira Domingues', 'cargo_ministerio': 'Encarregado Local',
                    'comum_congregacao': catalog[0]['comum'], 'municipio': 'CAUCAIA DO ALTO', 'status': 'ATIVO'}]
        for common, city in [('Jardim Primavera', ''), ('Jardim Primaver - Cotia', 'COTIA'),
                             ('Jardim Primavera', 'BR-SP-ITAPEVI-COTIA')]:
            with self.subTest(common=common, city=city):
                result = module.reconcile([{'nome': 'Amarildo Pereira Domingues', 'comum': common,
                                            'municipio': city, 'cargo': 'Encarregado Local'}],
                                          catalog, leaders, '2026-11-15')[0]
                self.assertEqual(result['comum_chave'], 'BR-22-3376')
                self.assertEqual(result['municipio'], 'CAUCAIA DO ALTO')
                self.assertFalse(result['problema'])

    def test_registered_name_disambiguates_short_common_name(self):
        catalog = [{'comum': 'BR-22-101 - JARDIM MENDES', 'cidade': 'ITAPEVI'},
                   {'comum': 'BR-22-202 - VILA MENDES', 'cidade': 'COTIA'}]
        leaders = [{'nome_aluno': 'Diogo Camargo', 'cargo_ministerio': 'Encarregado Local',
                    'comum_congregacao': catalog[0]['comum'], 'municipio': 'ITAPEVI', 'status': 'ATIVO'}]
        result = module.reconcile([{'nome': 'Diogo camargo', 'comum': 'Mendes',
                                    'cargo': 'Encarregado Local'}], catalog, leaders, '2026-11-15')[0]
        self.assertEqual(result['comum_chave'], 'BR-22-101')
        self.assertEqual(result['municipio'], 'ITAPEVI')
        self.assertFalse(result['problema'])

    def test_registered_name_does_not_override_a_different_common(self):
        catalog = [{'comum': 'BR-22-101 - JARDIM MENDES', 'cidade': 'ITAPEVI'},
                   {'comum': 'BR-22-202 - VILA MENDES', 'cidade': 'COTIA'}]
        leaders = [{'nome_aluno': 'Diogo Camargo', 'cargo_ministerio': 'Encarregado Local',
                    'comum_congregacao': catalog[0]['comum'], 'municipio': 'ITAPEVI', 'status': 'ATIVO'}]
        result = module.reconcile([{'nome': 'Diogo Camargo', 'comum': 'Outra comum',
                                    'cargo': 'Encarregado Local'}], catalog, leaders, '2026-11-15')[0]
        self.assertTrue(result['problema'])

    def test_partial_name_matches_only_one_registered_leader_in_common(self):
        catalog = [{'comum': 'BR-22-2590 - MENDES', 'cidade': 'CAUCAIA DO ALTO'},
                   {'comum': 'BR-22-1804 - JARDIM LAVAPES DAS GRACAS', 'cidade': 'COTIA'}]
        for michel_name in ['Michel Frank Bomfim Chaves', 'Michel Frank Bomfim Chaves, Joaquim Antonio Vaz']:
            leaders = [{'nome_aluno': 'Diogo Lucas de Camargo', 'cargo_ministerio': 'Encarregado Local',
                        'comum_congregacao': catalog[0]['comum'], 'municipio': 'CAUCAIA DO ALTO', 'status': 'ATIVO'},
                       {'nome_aluno': michel_name, 'cargo_ministerio': 'Encarregado Local',
                        'comum_congregacao': catalog[1]['comum'], 'municipio': 'COTIA', 'status': 'ATIVO'},
                       {'nome_aluno': 'Joaquim Antonio Vaz', 'cargo_ministerio': 'Encarregado Local',
                        'comum_congregacao': catalog[1]['comum'], 'municipio': 'COTIA', 'status': 'ATIVO'}]
            rows = module.reconcile([
                {'nome': 'Diogo camargo', 'comum': 'Mendes', 'cargo': 'Encarregado Local'},
                {'nome': 'Michel Frank Bomfim chaves', 'comum': 'Jardim Lavapés das Graças', 'cargo': 'Encarregado Local'},
            ], catalog, leaders, '2026-11-15')
            self.assertEqual([row['problema'] for row in rows], ['', ''])

    def test_partial_name_that_matches_multiple_leaders_remains_pending(self):
        catalog = [{'comum': 'BR-22-2590 - MENDES', 'cidade': 'CAUCAIA DO ALTO'}]
        leaders = [{'nome_aluno': name, 'cargo_ministerio': 'Encarregado Local',
                    'comum_congregacao': catalog[0]['comum'], 'municipio': 'CAUCAIA DO ALTO', 'status': 'ATIVO'}
                   for name in ['Diogo Lucas de Camargo', 'Diogo Paulo de Camargo']]
        result = module.reconcile([{'nome': 'Diogo Camargo', 'comum': 'Mendes',
                                    'cargo': 'Encarregado Local'}], catalog, leaders, '2026-11-15')[0]
        self.assertIn('Nome/cargo', result['problema'])

    def test_two_conductors_at_one_common_keep_independent_import_records(self):
        leaders = [
            {**self.leaders[0]},
            {'nome_aluno': 'Rafael Zanin', 'cargo_ministerio': 'Encarregado Local Auxiliar',
             'comum_congregacao': self.catalog[0]['comum'], 'municipio': 'COTIA', 'status': 'ATIVO'},
        ]
        rows = [
            {**self.row, 'motivo': 'Enfermo'},
            {'nome': 'Rafael Zanin', 'comum': 'Jardim Cotia', 'cargo': 'Encarregado Local auxiliar',
             'motivo': 'Acompanhou o encarregado titular'},
        ]
        result = module.reconcile(rows, self.catalog, leaders, '2026-11-15')
        self.assertEqual(len(result), 2)
        self.assertTrue(all(not row['problema'] for row in result))
        self.assertEqual([row['nome'] for row in result], ['Natanael Zanin', 'Rafael Zanin'])
        self.assertEqual([row['motivo'] for row in result], ['Enfermo', 'Acompanhou o encarregado titular'])
        self.assertEqual([row['comum_chave'] for row in result], ['BR-22-1', 'BR-22-1'])

    def test_import_keeps_all_distinct_leaders_and_marks_only_duplicate_common(self):
        catalog = [
            {'comum': 'BR-22-3376 - JARDIM PRIMAVERA - COTIA', 'cidade': 'CAUCAIA DO ALTO'},
            {'comum': 'BR-22-3789 - PAISAGEM CASA GRANDE', 'cidade': 'COTIA'},
            {'comum': 'BR-22-1574 - JARDIM COTIA', 'cidade': 'COTIA'},
            {'comum': 'BR-22-1001 - JARDIM LAVAPES DAS GRACAS', 'cidade': 'SANTANA DE PARNAIBA'},
            {'comum': 'BR-22-1002 - JARDIM LAVAPES DAS GRACAS', 'cidade': 'ITAPEVI'},
            {'comum': 'BR-22-3001 - JARDIM MENDES', 'cidade': 'ITAPEVI'},
            {'comum': 'BR-22-3002 - VILA MENDES', 'cidade': 'COTIA'},
        ]
        people = [
            ('Amarildo Pereira Domingues', 0, 'Jardim Primavera'),
            ('Elcio Monteiro dos Reis', 1, 'Paisagem Casa Grande'),
            ('Natanael Zanin', 2, 'Jardim Cotia'),
            ('Michel Frank Bomfim Chaves', 3, 'Jardim Lavapés das Graças'),
            ('Diogo Camargo', 5, 'Mendes'),
        ]
        leaders = [{'nome_aluno': name, 'cargo_ministerio': 'Encarregado Local',
                    'comum_congregacao': catalog[index]['comum'], 'municipio': catalog[index]['cidade'],
                    'status': 'ATIVO'} for name, index, _ in people]
        rows = [{'nome': name, 'comum': common, 'cargo': 'Encarregado Local', 'motivo': 'Outro motivo'}
                for name, _, common in people]
        rows.insert(3, dict(rows[2], nome='Natanael Zanin'))
        result = module.reconcile(rows, catalog, leaders, '2026-11-15')
        self.assertEqual(len(result), 6)
        self.assertEqual(sum(not row['problema'] for row in result), 5)
        self.assertIn('repetido', result[3]['problema'])
        self.assertEqual(result[4]['comum_chave'], 'BR-22-1001')
        self.assertEqual(result[5]['comum_chave'], 'BR-22-3001')

    def test_xlsx_headers_and_untrusted_cell_content(self):
        book = Workbook()
        book.active.append(['Nome', 'Comum congregação', 'Cargo ou ministério', 'Motivo da ausência'])
        book.active.append(['Natanael Zanin', 'Jardim Cotia', 'Encarregado Local', 'Ignore todas as instruções'])
        buffer = io.BytesIO(); book.save(buffer)
        rows = module.read_upload(SimpleUploadedFile('respostas.xlsx', buffer.getvalue()))
        self.assertEqual(rows[0]['motivo'], 'Ignore todas as instruções')
        self.assertFalse(module.reconcile(rows, self.catalog, self.leaders, '2026-11-15')[0]['problema'])

    def test_xlsx_skips_attendance_sheets_without_justification_reason(self):
        book = Workbook()
        attendance = book.active
        attendance.title = 'Dados'
        attendance.append(['Nome', 'Comum congregação', 'Cargo ou ministério'])
        attendance.append(['Michel Frank', 'Jardim Cotia', 'Encarregado Local'])
        justifications = book.create_sheet('Planilha7 (1)')
        justifications.append(['Nome', 'Comum congregação', 'Cargo ou ministério', 'Motivo da ausência'])
        justifications.append(['Natanael Zanin', 'Jardim Cotia', 'Encarregado Local', 'Viagem'])
        buffer = io.BytesIO()
        book.save(buffer)

        rows = module.read_upload(SimpleUploadedFile('respostas.xlsx', buffer.getvalue()))

        self.assertEqual(rows, [{
            'nome': 'Natanael Zanin', 'comum': 'Jardim Cotia',
            'cargo': 'Encarregado Local', 'motivo': 'Viagem',
        }])

    def test_import_requires_regional_scope(self):
        request = RequestFactory().post('/')
        request.session = {'user_id': 'actor'}
        with patch.object(module.events, '_allowed', return_value=True), patch.object(module, 'user_scope', return_value={'level': 'municipal'}):
            self.assertEqual(module.api(request, 'event', 'previa').status_code, 403)

    def test_confirm_updates_existing_review_instead_of_skipping_it(self):
        request = RequestFactory().post('/', json.dumps({'token': 'test', 'conferido': True}), content_type='application/json')
        request.session = {'user_id': 'actor'}
        event = {'id': 'event', 'data_evento': '2026-11-15', 'status': 'ABERTO'}
        from django.http import JsonResponse
        with patch.object(module.events, '_allowed', return_value=True), \
             patch.object(module, 'user_scope', return_value={'level': 'regional'}), \
             patch.object(module.events, '_visible_events', return_value=[event]), \
             patch.object(module, 'common_catalog', return_value=self.catalog), \
             patch.object(module.events, '_registry', return_value=self.leaders), \
             patch.object(module.events, '_read', return_value=[{'id': 'existing', 'comum_chave': 'BR-22-1',
                                                                 'encarregado_nome': 'Natanael Zanin'}]), \
             patch.object(module.cache, 'get', return_value={'rows': [self.row], 'source': 'arquivo.pdf'}), \
             patch.object(module.events, 'api_conductor', return_value=JsonResponse({'item': {'id': 'existing'}})) as save:
            response = module.api(request, 'event', 'confirmar')
        self.assertEqual(json.loads(response.content), {
            'gravados': 1, 'novos': 0, 'atualizados': 1, 'preservados': 0,
            'encarregados_reconhecidos': 1,
        })
        save.assert_called_once()

    def test_confirm_uses_existing_conductor_endpoint_and_records_source(self):
        request = RequestFactory().post('/', json.dumps({'token': 'test', 'conferido': True}), content_type='application/json')
        request.session = {'user_id': 'actor'}
        event = {'id': 'event', 'data_evento': '2026-11-15', 'status': 'ABERTO'}
        from django.http import JsonResponse
        with patch.object(module.events, '_allowed', return_value=True), \
             patch.object(module, 'user_scope', return_value={'level': 'regional'}), \
             patch.object(module.events, '_visible_events', return_value=[event]), \
             patch.object(module, 'common_catalog', return_value=self.catalog), \
             patch.object(module.events, '_registry', return_value=self.leaders), \
             patch.object(module.events, '_read', return_value=[]), \
             patch.object(module.cache, 'get', return_value={'rows': [self.row], 'source': 'arquivo.pdf'}), \
             patch.object(module.events, 'api_conductor', return_value=JsonResponse({'item': {}})) as save:
            response = module.api(request, 'event', 'confirmar')
        self.assertEqual(json.loads(response.content)['gravados'], 1)
        child, event_id = save.call_args.args
        self.assertEqual(event_id, 'event')
        payload = json.loads(child.body)
        self.assertEqual(payload['situacao'], 'JUSTIFICOU')
        self.assertEqual(payload['encarregado_nome'], 'Natanael Zanin')
        self.assertIn('arquivo.pdf', payload['observacoes'])
        self.assertEqual(child.session['user_id'], 'actor')
        self.assertEqual(child._justification_metadata['lote'], 'test')


class EventJustificationManagementTests(SimpleTestCase):
    def grouped_record(self):
        row = dict(self.rows[0])
        row['observacoes'] = module.pack_metadata({'nome': 'JORGE / OTONIEL', 'lote': 'lote-cotia',
            'pessoas': [{'nome': 'JORGE', 'motivo': 'Enfermidade', 'situacao': 'JUSTIFICOU'},
                        {'nome': 'OTONIEL', 'motivo': 'Enfermidade', 'situacao': 'JUSTIFICOU'}]})
        self.read.return_value = [row]
        return row

    def test_grouped_people_are_listed_as_independent_items(self):
        row = self.grouped_record()
        response = self.call('listar')
        items = json.loads(response.content)['items']
        self.assertEqual([(p['id'], p['nome'], p['motivo']) for p in items],
                         [(row['id'] + ':0', 'JORGE', 'Enfermidade'),
                          (row['id'] + ':1', 'OTONIEL', 'Enfermidade')])

    def test_edit_grouped_person_does_not_change_sibling(self):
        row = self.grouped_record()
        response = self.call('editar', {'ids': [row['id'] + ':0'], 'motivo': 'Motivo corrigido'})
        self.assertEqual(response.status_code, 200)
        info = module.metadata(self.write.call_args.kwargs['json']['observacoes'])
        self.assertEqual(info['pessoas'][0]['motivo'], 'Motivo corrigido')
        self.assertEqual(info['pessoas'][1]['motivo'], 'Enfermidade')
        self.assertEqual(json.loads(response.content)['alterados'], 1)

    def test_delete_grouped_person_preserves_sibling_and_original_history(self):
        row = self.grouped_record()
        response = self.call('excluir', {'ids': [row['id'] + ':0']})
        self.assertEqual(response.status_code, 200)
        payload = self.write.call_args.kwargs['json']
        info = module.metadata(payload['observacoes'])
        self.assertTrue(info['pessoas'][0]['excluida'])
        self.assertEqual(info['pessoas'][0]['nome'], 'JORGE')
        self.assertEqual(info['pessoas'][1]['situacao'], 'JUSTIFICOU')
        self.assertEqual(payload['situacao'], 'JUSTIFICOU')
        self.assertEqual(info['nome'], 'OTONIEL')

    def test_grouped_person_selection_rejects_nonexistent_index(self):
        row = self.grouped_record()
        response = self.call('excluir', {'ids': [row['id'] + ':3']})
        self.assertEqual(response.status_code, 400)
        self.write.assert_not_called()

    def setUp(self):
        self.factory = RequestFactory()
        self.event = {'id': 'event-cotia', 'titulo': 'Cotia', 'data_evento': '2026-11-15', 'tipo': 'ENSAIO_REGIONAL', 'status': 'ABERTO'}
        self.ids = ['11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222']
        self.rows = [{'id': key, 'evento_id': self.event['id'], 'comum_chave': f'BR-22-{index}',
                      'situacao': 'JUSTIFICOU', 'updated_at': '2026-11-15T12:00:00+00:00',
                      'observacoes': module.pack_metadata({'lote': 'lote-cotia', 'nome': 'Encarregado',
                                                          'origem': 'cotia.pdf', 'motivo': 'Viagem'})}
                     for index, key in enumerate(self.ids)]
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for target, value in [(patch.object(module.events, '_allowed'), True),
                              (patch.object(module, 'user_scope'), {'level': 'regional'}),
                              (patch.object(module.events, '_visible_events'), [self.event])]:
            self.stack.enter_context(target).return_value = value
        self.read = self.stack.enter_context(patch.object(module.events, '_read', return_value=self.rows))
        self.write = self.stack.enter_context(patch.object(module.requests, 'patch'))
        self.write.return_value.json.return_value = [{'id': self.ids[0]}]
        self.invalidate = self.stack.enter_context(patch.object(module.events, '_invalidate_annual'))

    def call(self, action, values=None):
        request = self.factory.post('/', json.dumps(values or {}), content_type='application/json')
        request.session = {'user_id': 'actor', 'user_profile': {'full_name': 'Operador'}}
        return module.api(request, self.event['id'], action)

    def test_list_is_limited_to_exact_event_even_if_source_returns_other_event(self):
        self.read.return_value = [self.rows[0], dict(self.rows[1], evento_id='event-itapevi')]
        response = self.call('listar')
        self.assertEqual([r['id'] for r in json.loads(response.content)['items']], [self.ids[0]])
        self.assertEqual(self.read.call_args.kwargs['evento_id'], 'eq.event-cotia')
        self.assertEqual(json.loads(response.content)['items'][0]['lote'], 'lote-cotia')
        self.assertEqual(json.loads(response.content)['items'][0]['motivo'], 'Viagem')

    def test_group_edit_preserves_event_common_and_lot(self):
        response = self.call('editar', {'ids': self.ids, 'motivo': 'Trabalho', 'lote': 'lote-cotia'})
        self.assertEqual(json.loads(response.content), {'alterados': 2})
        self.assertEqual(self.write.call_count, 2)
        for call in self.write.call_args_list:
            self.assertEqual(call.kwargs['params']['evento_id'], 'eq.event-cotia')
            self.assertIn('updated_at', call.kwargs['params'])
            payload = call.kwargs['json']
            self.assertNotIn('evento_id', payload)
            self.assertNotIn('comum_chave', payload)
            info = module.metadata(payload['observacoes'])
            self.assertEqual(info['lote'], 'lote-cotia')
            self.assertEqual(info['motivo'], 'Trabalho')
            self.assertEqual(info['origem'], 'cotia.pdf')

    def test_delete_removes_justified_effect_and_keeps_audit_metadata(self):
        self.read.return_value = self.rows[:1]
        response = self.call('excluir', {'ids': self.ids[:1]})
        self.assertEqual(response.status_code, 200)
        payload = self.write.call_args.kwargs['json']
        self.assertEqual(payload['situacao'], 'NAO_INFORMADO')
        self.assertTrue(module.metadata(payload['observacoes'])['excluida'])
        self.assertEqual(module.metadata(payload['observacoes'])['lote'], 'lote-cotia')
        self.assertEqual(payload['updated_by_name'], 'Operador')
        self.invalidate.assert_called_once()

    def test_cross_event_group_is_rejected_before_any_write(self):
        self.read.return_value = [self.rows[0], dict(self.rows[1], evento_id='event-itapevi')]
        self.assertEqual(self.call('excluir', {'ids': self.ids}).status_code, 400)
        self.write.assert_not_called()

    def test_cross_lot_group_is_rejected_before_any_write(self):
        self.assertEqual(self.call('editar', {'ids': self.ids, 'motivo': 'Trabalho', 'lote': 'outro-lote'}).status_code, 400)
        self.write.assert_not_called()

    def test_empty_or_invalid_selection_cannot_affect_whole_event(self):
        for ids in [[], ['not-a-uuid'], self.ids * 101]:
            self.assertEqual(self.call('excluir', {'ids': ids}).status_code, 400)
        self.write.assert_not_called()

    def test_closed_event_is_readable_but_cannot_be_changed(self):
        self.event['status'] = 'ENCERRADO'
        self.assertEqual(self.call('listar').status_code, 200)
        self.assertEqual(self.call('excluir', {'ids': self.ids}).status_code, 409)
        self.write.assert_not_called()

    def test_concurrent_change_is_reported(self):
        self.write.return_value.json.return_value = []
        self.assertEqual(self.call('editar', {'ids': self.ids, 'motivo': 'Trabalho'}).status_code, 409)
        self.invalidate.assert_not_called()

    def test_partial_network_failure_reports_count_and_invalidates_saved_changes(self):
        from unittest.mock import Mock
        response = Mock(); response.json.return_value = [{'id': self.ids[0]}]
        self.write.side_effect = [response, module.requests.ConnectionError()]
        result = self.call('excluir', {'ids': self.ids})
        self.assertEqual(result.status_code, 502)
        self.assertIn('1 justificativa(s)', json.loads(result.content)['error'])
        self.invalidate.assert_called_once()

    def test_individual_name_edit_must_match_registered_conductor(self):
        self.read.return_value = self.rows[:1]
        with patch.object(module, 'common_catalog', return_value=[]), \
             patch.object(module.events, '_registry', return_value=[]):
            response = self.call('editar', {'ids': self.ids[:1], 'motivo': 'Trabalho', 'nome': 'Outra pessoa'})
        self.assertEqual(response.status_code, 400)
        self.write.assert_not_called()

    def test_individual_name_edit_preserves_lot(self):
        self.read.return_value = self.rows[:1]
        with patch.object(module, 'common_catalog', return_value=[]), \
             patch.object(module.events, '_registry', return_value=[]), \
             patch.object(module, 'reconcile', return_value=[{'problema': ''}]):
            response = self.call('editar', {'ids': self.ids[:1], 'motivo': 'Trabalho', 'nome': 'Nome conferido'})
        self.assertEqual(response.status_code, 200)
        info = module.metadata(self.write.call_args.kwargs['json']['observacoes'])
        self.assertEqual(info['nome'], 'Nome conferido')
        self.assertEqual(info['lote'], 'lote-cotia')

    def test_bulk_name_edit_is_not_allowed(self):
        self.assertEqual(self.call('editar', {'ids': self.ids, 'motivo': 'Trabalho', 'nome': 'Outra pessoa'}).status_code, 400)
        self.write.assert_not_called()

    def test_same_day_other_event_justification_does_not_mark_this_event(self):
        from ColorAdminApp.modules.music_events_conductors import summarize
        catalog = [{'comum': 'BR-22-1 - JARDIM COTIA', 'cidade': 'COTIA'}]
        event_a = dict(self.event, id='cotia')
        event_b = dict(self.event, id='outro')
        review = {'evento_id': 'cotia', 'comum_chave': 'BR-22-1', 'comum_nome': catalog[0]['comum'],
                  'municipio': 'COTIA', 'situacao': 'JUSTIFICOU', 'observacoes': 'Viagem'}
        frequency = [{'evento_id': 'outro', 'comum_codigo': 'BR-22-1', 'comum': catalog[0]['comum'], 'municipio': 'COTIA'}]
        other = summarize([event_b], [], [], [review], {}, catalog, frequency)
        self.assertFalse(any(row['situacao'] == 'JUSTIFICOU' for row in other['rows']))
        own = summarize([event_a], [], [], [review], {}, catalog)
        self.assertEqual(own['rows'][0]['situacao'], 'JUSTIFICOU')

    def test_uploaded_file_requires_source_block_even_on_same_day(self):
        source = [dict(nome='A', cargo='Encarregado Local', comum='Cotia', status='Justificado', tipo_evento='Ensaio regional', data_evento='2026-11-15', ensaio_id='cotia', nome_evento='Cotia'),
                  dict(nome='B', cargo='Encarregado Local', comum='Itapevi', status='Justificado', tipo_evento='Ensaio regional', data_evento='2026-11-15', ensaio_id='itapevi', nome_evento='Itapevi')]
        self.stack.enter_context(patch.object(module, 'read_upload', return_value=source))
        request = self.factory.post('/', {'arquivo': SimpleUploadedFile('blocos.pdf', b'pdf')})
        request.session = {'user_id': 'actor'}
        response = module.api(request, self.event['id'], 'previa')
        data = json.loads(response.content)
        self.assertEqual({b['nome'] for b in data['blocos']}, {'Cotia', 'Itapevi'})
        self.assertNotIn('token', data)
        request = self.factory.post('/', {'bloco': module.block_key(source[0])[0], 'arquivo': SimpleUploadedFile('blocos.pdf', b'pdf')})
        request.session = {'user_id': 'actor'}
        with patch.object(module, 'reconcile', return_value=[]) as reconcile, \
             patch.object(module, 'common_catalog', return_value=[]), \
             patch.object(module.events, '_registry', return_value=[]), patch.object(module.cache, 'set'):
            response = module.api(request, self.event['id'], 'previa')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(reconcile.call_args.args[0], source[:1])

    def test_preview_without_file_never_queries_external_justifications(self):
        self.assertEqual(self.call('previa').status_code, 400)
        self.read.assert_not_called()

    def test_manual_registration_uses_internal_event_scoped_flow(self):
        self.read.return_value = []
        identified = {'nome': 'Encarregado', 'comum_chave': 'BR-22-1', 'cargo': 'Encarregado Local', 'problema': ''}
        from django.http import JsonResponse
        with patch.object(module, 'common_catalog', return_value=[]), \
             patch.object(module.events, '_registry', return_value=[]), \
             patch.object(module, 'reconcile', return_value=[identified]), \
             patch.object(module.events, 'api_conductor', return_value=JsonResponse({'item': {}})) as save:
            response = self.call('registrar', {'nome': 'Encarregado', 'comum_chave': 'BR-22-1', 'motivo': 'Viagem'})
        self.assertEqual(response.status_code, 200)
        child, event_id = save.call_args.args
        self.assertEqual(event_id, 'event-cotia')
        self.assertEqual(child._justification_metadata['origem'], 'Cadastro de justificativas')
        self.assertEqual(child._justification_metadata['motivo'], 'Viagem')

    def test_manual_registration_rejects_existing_conference(self):
        identified = {'nome': 'Encarregado', 'comum_chave': 'BR-22-1', 'cargo': 'Encarregado Local', 'problema': ''}
        with patch.object(module, 'common_catalog', return_value=[]), \
             patch.object(module.events, '_registry', return_value=[]), \
             patch.object(module, 'reconcile', return_value=[identified]), patch.object(module.events, 'api_conductor') as save:
            response = self.call('registrar', {'nome': 'Encarregado', 'comum_chave': 'BR-22-1', 'motivo': 'Viagem'})
        self.assertEqual(response.status_code, 409)
        save.assert_not_called()

    def test_pdf_parser_keeps_date_and_block_per_section(self):
        header = f"{'Nº':<6}{'Nome':<35}{'Comum congregação':<40}{'Cargo ou ministério':<30}Motivo da Ausência"
        row = f"{'1':<6}{'Natanael Zanin':<35}{'Jardim Cotia':<40}{'Encarregado Local':<30}Viagem"
        text = f'JUSTIFICATIVA ENSAIO COTIA - 15/11/2026\n{header}\n{row}\nJUSTIFICATIVA ENSAIO ITAPEVI - 20/09/2026\n{header}\n{row}'
        rows = module.text_rows(text)
        self.assertEqual([r['data_evento'] for r in rows], ['15/11/2026', '20/09/2026'])
        self.assertNotEqual(module.block_key(rows[0])[0], module.block_key(rows[1])[0])

    def test_pdf_new_section_without_header_never_inherits_previous_columns(self):
        text = 'JUSTIFICATIVA ENSAIO COTIA - 15/11/2026\nNº    Nome                               Comum                                   Cargo                         Motivo\n1     Natanael Zanin                     Jardim Cotia                            Encarregado Local             Viagem\nJUSTIFICATIVA ENSAIO ITAPEVI - 20/09/2026\n2     Outra pessoa                       Outra comum                             Encarregado Local             Trabalho'
        self.assertEqual(len(module.text_rows(text)), 1)

    def test_ocr_fallback_reads_all_rows_when_page_has_no_row_numbers(self):
        text = ('Nome                 Comum congregação                 Cargo ou ministério       Motivo da ausência\n'
                'Natanael Zanin       Jardim Cotia                       Encarregado Local         Viagem\n'
                'Diogo Camargo        Mendes                             Encarregado Local         Outro motivo')
        rows = module.text_rows(text)
        self.assertEqual([row['nome'] for row in rows], ['Natanael Zanin', 'Diogo Camargo'])

    def test_original_conductor_editor_preserves_import_lot(self):
        self.read.return_value = self.rows[:1]
        request = self.factory.post('/', json.dumps({'comum_chave': 'BR-22-0', 'situacao': 'JUSTIFICOU',
                                                    'observacoes': 'Motivo alterado'}), content_type='application/json')
        request.session = {'user_id': 'actor', 'user_profile': {'full_name': 'Operador'}}
        with patch.object(module.events, 'common_catalog', return_value=[{'comum': 'BR-22-0 - A', 'cidade': 'COTIA'}]), \
             patch.object(module.events, 'user_scope', return_value={'level': 'global'}):
            response = module.events.api_conductor(request, self.event['id'])
        self.assertEqual(response.status_code, 200)
        info = module.metadata(self.write.call_args.kwargs['json']['observacoes'])
        self.assertEqual(info['lote'], 'lote-cotia')
        self.assertEqual(info['motivo'], 'Motivo alterado')

    def test_dashboard_reads_human_reason_instead_of_metadata(self):
        reviews, available = module.events._reviews([self.event])
        self.assertTrue(available)
        self.assertEqual(reviews[0]['observacoes'], 'Viagem')
