import io
from datetime import datetime
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from django.core.cache import cache
from pypdf import PdfReader

from ColorAdminApp.modules import music_events
from ColorAdminApp.modules.music_events_annual import annual_data
from ColorAdminApp.modules.music_events_annual_reports import build_annual_pdf


def fixture():
    catalog = [{'comum': 'BR-22-1 - Central', 'cidade': 'ITAPEVI'},
               {'comum': 'BR-22-2 - Sem participação', 'cidade': 'ITAPEVI'},
               {'comum': 'BR-22-3 - Vila de Cotia', 'cidade': 'COTIA'},
               {'comum': 'BR-22-4 - Vila de Caucaia', 'cidade': 'CAUCAIA DO ALTO'},
               {'comum': 'BR-22-5 - Vila de VGP', 'cidade': 'VARGEM GRANDE PAULISTA'}]
    events = [{'id': key, 'titulo': key, 'tipo': 'ENSAIO_REGIONAL', 'familia': 'GERAL',
               'data_evento': day, 'status': 'ABERTO', 'base_id': None}
              for key, day in [('jan', '2026-01-18'), ('may', '2026-05-17'), ('sep', '2026-09-20'),
                               ('cotia', '2026-03-15'), ('caucaia', '2026-03-15'), ('vgp', '2026-03-15')]]
    sites = [{'id': e['id'] + '-site', 'evento_id': e['id'],
              'nome': {'cotia': 'COTIA', 'caucaia': 'CAUCAIA DO ALTO', 'vgp': 'VGP'}.get(e['id'], 'ITAPEVI')}
             for e in events]
    registry = []
    for common in catalog:
        for i, instrument in enumerate(['VIOLINO'] * 4 + ['ORGAO'] * 2):
            registry.append({'id': common['comum'][:7] + str(i), 'nome_aluno': 'Nome ' + str(i),
                             'comum_congregacao': common['comum'], 'municipio': common['cidade'],
                             'instrumento': instrument, 'status': 'ATIVO', 'nivel': 'Oficializado',
                             'updated_at': '2026-10-24T10:00:00Z'})
    # IDs devem ser únicos em todo o cadastro SAM.
    for index, row in enumerate(registry):
        row['id'] = str(index)
    records = [{'id': e['id'] + '-p', 'evento_id': e['id'], 'local_id': e['id'] + '-site',
                'comum_codigo': 'BR-22-1', 'comum_informada': 'BR-22-1 - Central',
                'municipio_informado': 'ITAPEVI', 'categoria': 'MUSICO', 'familia': 'CORDAS',
                'sam_pessoa_id': '1', 'cargo': 'ENCARREGADO LOCAL', 'nome': 'Encarregado Teste'}
               for e in events[:3]]
    # Músico de Cotia presente em Caucaia; registros em vários locais na mesma data.
    for key in ['cotia', 'caucaia', 'vgp']:
        records.append({'id': key + '-p', 'evento_id': key, 'local_id': key + '-site',
                        'comum_codigo': 'BR-22-3', 'municipio_informado': 'COTIA', 'categoria': 'MUSICO',
                        'familia': 'CORDAS', 'sam_pessoa_id': 'other', 'cargo': 'ENCARREGADO LOCAL', 'nome': 'Outro Encarregado'})
    return events, records, sites, registry, catalog


class AnnualMonitoringTests(SimpleTestCase):
    def test_comparison_uses_previous_loaded_date_from_the_same_circuit(self):
        from ColorAdminApp.modules.music_events_annual import annual_comparison
        e,r,s,registry,catalog=fixture()
        e.append(dict(e[0],id='july',data_evento='2026-07-19'))
        s.append({'id':'july-site','evento_id':'july','nome':'COTIA'})
        r.append(dict(r[0],id='july-person',evento_id='july',local_id='july-site'))
        data=annual_data(e,r,s,registry,catalog,[],[],[],2026,{'level':'regional'},['ITAPEVI'])
        comparison=annual_comparison(data,'2026-09-20')
        self.assertEqual(comparison['previous']['date'],'2026-05-17')
        self.assertEqual(comparison['current']['commons'],2)
        self.assertEqual(comparison['previous']['commons'],2)
        self.assertNotIn('2026-07-19',[point['date'] for point in comparison['series']])
        self.assertIsNone(annual_comparison(data,'2026-01-18')['previous'])
        regional=annual_data(e,r,s,registry,catalog,[],[],[],2026,{'level':'regional'})
        regional_comparison=annual_comparison(regional,'2026-09-20')
        self.assertEqual(regional_comparison['previous']['date'],'2026-05-17')
        self.assertEqual(regional_comparison['current']['commons'],regional_comparison['previous']['commons'])

    def test_summary_dashboard_has_comparison_and_no_legend(self):
        from ColorAdminApp.modules.music_events_annual_reports import build_annual_pdf
        data=self.data(cities=['ITAPEVI'])
        pdf=PdfReader(io.BytesIO(build_annual_pdf(data,'TESTE',datetime(2026,10,24,18,30),'2026-09-20')))
        panel=next(page.extract_text() for page in pdf.pages if 'PAINEL DE PARTICIPAÇÃO' in page.extract_text())
        self.assertNotIn('LEGENDA',panel)
        self.assertIn('17/05/2026',panel)
        self.assertIn('20/09/2026',panel)
        self.assertIn('COMPARATIVO COM O ENSAIO ANTERIOR',panel)

    def test_may_cotia_destination_is_pending_without_inventing_itapevi_attendance(self):
        from ColorAdminApp.modules.music_events_annual_reports import session_report, build_model_pdf
        e, r, s, registry, catalog = fixture()
        next(site for site in s if site['evento_id'] == 'may')['nome'] = 'COTIA'
        data = annual_data(e, r, s, registry, catalog, [], [], [], 2026, {'level': 'regional'}, ['ITAPEVI'])
        cell = next(row for row in data['rows'] if row['key'] == 'BR-22-1')['cells'][1]
        self.assertEqual(cell['musicians'], 1)
        self.assertEqual(cell['leader_status'], 'PRESENTE')
        self.assertEqual(cell['leader_locations'], ['LOCAL A CONFERIR'])
        report = session_report(data, next(session for session in data['sessions'] if session['date'] == '2026-05-17'))
        report['allow_original'] = False
        pdf = PdfReader(io.BytesIO(build_model_pdf(report)))
        text = '\n'.join(page.extract_text() for page in pdf.pages)
        self.assertIn('PRESENTE', text)
        self.assertNotIn('LOCAL A CONFERIR', text)
        self.assertNotIn('COTIA', text)
        self.assertEqual(text, text.upper())

    def test_original_closing_and_origin_scope_are_distinct(self):
        from ColorAdminApp.modules.music_events_annual_reports import session_report, build_model_pdf
        from ColorAdminApp.modules.music_events_closing import closing_for
        data = self.data(cities=['ITAPEVI'])
        report = session_report(data, next(s for s in data['sessions'] if s['date'] == '2026-05-17'))
        report['physical_closings'] = [{'date': '2026-05-17', 'city': 'ITAPEVI', 'total': 2092}]
        closing = closing_for(report)
        self.assertEqual(closing['total'], 2440)
        self.assertEqual(closing['nominal_total'], 2092)
        self.assertEqual(sum(closing['instruments'].values()), closing['musicians'])
        pdf = PdfReader(io.BytesIO(build_model_pdf(report, include_original=False)))
        text = '\n'.join(p.extract_text() for p in pdf.pages)
        self.assertIn('2440', text)
        self.assertEqual(closing['nominal_total'], 2092)
        self.assertEqual(closing['total'] - closing['nominal_total'], 348)
        self.assertIn('TOTAL GERAL DO LOCAL', text)
        last = pdf.pages[-1].extract_text()
        self.assertLess(last.index('VIOLINO'), last.index('CLARINETE'))
        self.assertLess(last.index('CLARINETE'), last.index('TROMPETE'))
        self.assertIn('MADEIRAS', last)

    def test_physical_closing_counts_all_origins_at_the_selected_site(self):
        from ColorAdminApp.modules.music_events_closing import physical_closings
        events, records, sites, _, _ = fixture()
        records.append(dict(records[0], id='visitor', municipio_informado='COTIA', comum_codigo='BR-22-3'))
        totals = physical_closings(events, records, sites)
        jan = next(row for row in totals if row['date'] == '2026-01-18' and row['city'] == 'ITAPEVI')
        self.assertEqual(jan['total'], 2)
        self.assertEqual(jan['musicians'], 2)

    def test_regular_calendar_destinations_for_both_circuits(self):
        from ColorAdminApp.modules.music_events_calendar import valid_destination
        for month in [1, 5, 9]:
            event = {'id': 'e', 'tipo': 'ENSAIO_REGIONAL', 'data_evento': f'2026-{month:02}-17'}
            self.assertTrue(valid_destination(event, {'evento_id': 'e', 'nome': 'PIRAPORA'}))
            self.assertFalse(valid_destination(event, {'evento_id': 'e', 'nome': 'COTIA'}))
        for month in [3, 7, 11]:
            event = {'id': 'e', 'tipo': 'ENSAIO_REGIONAL', 'data_evento': f'2026-{month:02}-17'}
            self.assertTrue(valid_destination(event, {'evento_id': 'e', 'nome': 'COTIA'}))
            self.assertTrue(valid_destination(event, {'evento_id': 'e', 'nome': 'VARGEM GRANDE'}))
            self.assertTrue(valid_destination(event, {'evento_id': 'e', 'nome': 'FAZENDINHA'}))
            self.assertFalse(valid_destination(event, {'evento_id': 'e', 'nome': 'ITAPEVI'}))

    def data(self, **kwargs):
        e, r, s, registry, catalog = fixture()
        return annual_data(e, r, s, registry, catalog, [], [], [], 2026, {'level': 'regional'}, **kwargs)

    def test_all_commons_include_zero_attendance_across_three_dates(self):
        data = self.data(cities=['ITAPEVI'])
        self.assertEqual(len(data['rows']), 2)
        absent = next(r for r in data['rows'] if r['key'] == 'BR-22-2')
        self.assertEqual(absent['loaded_sessions'], 3)
        self.assertTrue(absent['no_participation'])
        self.assertTrue(absent['year_complete'])
        self.assertEqual([c['musicians'] for c in absent['cells']], [0, 0, 0])
        self.assertTrue(all(c['musician_percent'] == 0 for c in absent['cells']))
        self.assertTrue(all(c['leader_status'] == 'NAO_INFORMADO' for c in absent['cells']))

    def test_same_day_joint_administration_does_not_multiply_sam_or_people(self):
        data = self.data(cities=['COTIA', 'CAUCAIA DO ALTO', 'VARGEM GRANDE PAULISTA'])
        cotia = next(r for r in data['rows'] if r['key'] == 'BR-22-3')
        self.assertEqual(cotia['loaded_sessions'], 1)
        self.assertEqual(cotia['musicians'], 1)
        self.assertEqual(cotia['cadastro_musicos'], 4)
        self.assertEqual(cotia['musician_percent'], 25)
        self.assertEqual(cotia['cells'][0]['leader_locations'], ['CAUCAIA DO ALTO', 'COTIA', 'VGP'])
        self.assertFalse(cotia['year_complete'])

    def test_unimported_dates_are_not_absences(self):
        e, r, s, registry, catalog = fixture()
        r = [person for person in r if person['evento_id'] not in {'may', 'sep'}]
        data = annual_data(e, r, s, registry, catalog, [], [], [], 2026, {'level': 'regional'}, ['ITAPEVI'])
        row = next(r for r in data['rows'] if r['key'] == 'BR-22-2')
        self.assertEqual(row['loaded_sessions'], 1)
        self.assertFalse(row['year_complete'])
        self.assertEqual([c['musicians'] for c in row['cells']], [0, None, None])

    def test_municipal_scope_cannot_export_other_municipalities(self):
        e, r, s, registry, catalog = fixture()
        data = annual_data(e, r, s, registry, catalog, [], [], [], 2026,
                           {'level': 'municipal', 'municipio': 'ITAPEVI'}, ['COTIA'])
        self.assertEqual(data['rows'], [])
        data = annual_data(e, r, s, registry, catalog, [], [], [], 2026,
                           {'level': 'municipal', 'municipio': 'ITAPEVI'})
        self.assertEqual(data['selected_cities'], ['ITAPEVI'])
        self.assertEqual(next(r for r in data['rows'] if r['key'] == 'BR-22-2')['loaded_sessions'], 3)

    def test_missing_base_does_not_produce_fake_zero_percent(self):
        e, r, s, registry, catalog = fixture()
        data = annual_data(e, r, s, [], catalog, [], [], [], 2026, {'level': 'regional'}, ['ITAPEVI'])
        self.assertIsNone(data['rows'][0]['cells'][0]['musician_percent'])

    def test_registered_sam_conductor_matches_nominal_presence_without_imported_role(self):
        e, r, s, registry, catalog = fixture()
        registry[0].update(nome_aluno='Encarregado Teste', cargo_ministerio='ENCARREGADO LOCAL')
        r[0]['cargo'] = ''
        data = annual_data(e, r, s, registry, catalog, [], [], [], 2026, {'level': 'regional'}, ['ITAPEVI'])
        row = next(row for row in data['rows'] if row['key'] == 'BR-22-1')
        self.assertEqual(row['leader_sessions'], 3)

    def test_explicit_justification_is_preserved(self):
        e, r, s, registry, catalog = fixture()
        review = {'evento_id': 'jan', 'comum_chave': 'BR-22-2', 'municipio': 'ITAPEVI',
                  'comum_nome': 'Sem participação', 'situacao': 'JUSTIFICOU'}
        data = annual_data(e, r, s, registry, catalog, [review], [], [], 2026, {'level': 'regional'}, ['ITAPEVI'])
        row = next(row for row in data['rows'] if row['key'] == 'BR-22-2')
        self.assertEqual(row['cells'][0]['leader_status'], 'JUSTIFICOU')

    def test_existing_invitation_status_and_calendar_override_are_preserved(self):
        e, r, s, registry, catalog = fixture()
        invitations = [{'evento_id': 'cotia', 'comum_codigo': 'BR-22-2',
                        'encarregado_situacao': 'JUSTIFICOU', 'encarregado_observacoes': 'Justificativa recebida'}]
        data = annual_data(e, r, s, registry, catalog, [], [], invitations, 2026,
                           {'level': 'regional'}, ['ITAPEVI'])
        row = next(row for row in data['rows'] if row['key'] == 'BR-22-2')
        cell = next(cell for cell in row['cells'] if cell['date'] == '2026-03-15')
        self.assertEqual(cell['leader_status'], 'JUSTIFICOU')

    def test_homonyms_with_distinct_ids_are_not_merged(self):
        e, r, s, registry, catalog = fixture()
        r.append(dict(r[0], id='different-person', sam_pessoa_id='another-id'))
        data = annual_data(e, r, s, registry, catalog, [], [], [], 2026, {'level': 'regional'}, ['ITAPEVI'])
        row = next(row for row in data['rows'] if row['key'] == 'BR-22-1')
        self.assertEqual(row['cells'][0]['musicians'], 2)

    def test_zero_population_is_not_an_artificial_percent(self):
        e, r, s, registry, catalog = fixture()
        registry = [row for row in registry if row['instrumento'] != 'ORGAO']
        data = annual_data(e, r, s, registry, catalog, [], [], [], 2026, {'level': 'regional'}, ['ITAPEVI'])
        row = data['rows'][0]
        self.assertEqual(row['cadastro_organistas'], 0)
        self.assertIsNone(row['cells'][0]['organist_percent'])

    def test_year_without_events_still_lists_catalog_without_false_absences(self):
        _, _, _, registry, catalog = fixture()
        data = annual_data([], [], [], registry, catalog, [], [], [], 2025, {'level': 'regional'}, ['ITAPEVI'])
        self.assertEqual(len(data['rows']), 2)
        self.assertTrue(all(row['loaded_sessions'] == 0 and not row['no_participation'] for row in data['rows']))
        pdf = PdfReader(io.BytesIO(build_annual_pdf(data, 'Teste', datetime(2026, 10, 24))))
        self.assertGreaterEqual(len(pdf.pages), 1)

    def test_unresolved_common_keeps_zero_records_visible_for_review(self):
        e, r, s, registry, catalog = fixture()
        r.append(dict(r[0], id='unresolved', comum_codigo=None, comum_informada='Nome desconhecido'))
        data = annual_data(e, r, s, registry, catalog, [], [], [], 2026, {'level': 'regional'}, ['ITAPEVI'])
        row = next(row for row in data['rows'] if row['key'] == 'BR-22-2')
        self.assertTrue(row['unresolved'])
        self.assertTrue(row['no_participation'])
        self.assertTrue(row['absence_review_pending'])

    def test_pdf_has_annual_matrix_model_and_municipality_separation(self):
        data = self.data(cities=['ITAPEVI'])
        content = build_annual_pdf(data, 'Operador de teste', datetime(2026, 10, 24, 12, 30))
        pdf = PdfReader(io.BytesIO(content))
        text = '\n'.join(page.extract_text() for page in pdf.pages)
        self.assertIn('ANO DE ACOMPANHAMENTO', text)
        self.assertIn('CADASTRO SAM ATUAL', text)
        self.assertIn('ENCARREGADO LOCAL CADASTRADO', text)
        self.assertNotIn('M / O', text)
        self.assertNotIn('Enc.:', text)
        self.assertIn('RELATÓRIO UNIFICADO ENSAIO REGIONAL', text)
        self.assertIn('PRESENÇA ENCARREGADOS', text)
        self.assertIn('SEM PARTICIPAÇÃO', text)
        self.assertNotIn('VILA DE COTIA', text)
        self.assertGreaterEqual(len(pdf.pages), 10)
        self.assertIn('FECHAMENTO DO ENSAIO REGIONAL', text)
        self.assertNotIn('ANEXO ORIGINAL', text)

    def test_origin_filter_does_not_turn_an_attendance_site_into_another_municipality(self):
        from ColorAdminApp.modules.music_events_annual_reports import session_report, build_model_pdf
        e, r, s, registry, catalog = fixture()
        next(site for site in s if site['evento_id'] == 'sep')['nome'] = 'PIRAPORA'
        data = annual_data(e, r, s, registry, catalog, [], [], [], 2026, {'level': 'regional'}, ['ITAPEVI'])
        report = session_report(data, next(session for session in data['sessions'] if session['date'] == '2026-09-20'))
        report['allow_original'] = False
        pdf = PdfReader(io.BytesIO(build_model_pdf(report)))
        text = '\n'.join(page.extract_text() for page in pdf.pages)
        self.assertNotIn('ITAPEVI E PIRAPORA', text)
        self.assertIn('MÚSICOS DE ITAPEVI', text)
        self.assertNotIn('MÚSICOS DE PIRAPORA', text)
        self.assertEqual({row['municipio'] for row in report['rows']}, {'ITAPEVI'})
        self.assertEqual(report['municipalities'][0]['MUSICO'], 1)
        self.assertIn('PIRAPORA', report['conductors']['rows'][0]['locais'])

    def test_pdf_builder_enforces_city_filter_even_if_it_receives_extra_commons(self):
        from ColorAdminApp.modules.music_events_annual_reports import build_model_pdf
        data = self.data()
        from ColorAdminApp.modules.music_events_annual_reports import session_report
        report = session_report(data, next(session for session in data['sessions'] if session['date'] == '2026-03-15'))
        report['filters']['municipios'] = ['COTIA']
        report['allow_original'] = False
        pdf = PdfReader(io.BytesIO(build_model_pdf(report)))
        text = '\n'.join(page.extract_text() for page in pdf.pages)
        self.assertIn('VILA DE COTIA', text)
        self.assertNotIn('VILA DE CAUCAIA', text)
        self.assertNotIn('VILA DE VGP', text)

    @patch.object(music_events, '_allowed', return_value=False)
    def test_annual_endpoints_require_permission(self, allowed):
        request = RequestFactory().get('/')
        self.assertEqual(music_events.api_annual(request).status_code, 403)
        self.assertEqual(music_events.export_annual(request).status_code, 403)

    def test_raw_cache_reapplies_scope_and_is_invalidated_after_changes(self):
        e, r, s, registry, catalog = fixture()
        sources = dict(events=e, records=r, sites=s, registry=registry, catalog=catalog,
                       reviews=[], members=[], invitations=[], review_available=True)
        music_events._invalidate_annual()
        request = RequestFactory().get('/', {'ano': '2026'})
        with patch.object(music_events, '_annual_sources', return_value=sources) as read, \
                patch.object(music_events, 'user_scope') as scope:
            scope.return_value = {'level': 'regional'}
            self.assertEqual(len(music_events.annual_dashboard_data(request)['rows']), 5)
            scope.return_value = {'level': 'municipal', 'municipio': 'ITAPEVI'}
            result = music_events.annual_dashboard_data(request)
            self.assertEqual(result['selected_cities'], ['ITAPEVI'])
            self.assertEqual(read.call_count, 1)
            music_events._invalidate_annual()
            music_events.annual_dashboard_data(request)
            self.assertEqual(read.call_count, 2)

    def test_pdf_export_keeps_the_selected_followup_filter(self):
        e, r, s, registry, catalog = fixture()
        sources = dict(events=e, records=r, sites=s, registry=registry, catalog=catalog,
                       reviews=[], members=[], invitations=[], review_available=True)
        music_events._invalidate_annual()
        request = RequestFactory().get('/', {'ano': '2026', 'situacao': 'no_participation', 'municipio': 'ITAPEVI'})
        with patch.object(music_events, '_annual_sources', return_value=sources), \
                patch.object(music_events, 'user_scope', return_value={'level': 'regional'}):
            result = music_events.annual_dashboard_data(request)
        self.assertEqual([r['key'] for r in result['rows']], ['BR-22-2'])
