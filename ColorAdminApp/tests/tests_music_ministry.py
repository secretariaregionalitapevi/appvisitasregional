from datetime import datetime
from io import BytesIO
from unittest.mock import patch
import json

from django.test import RequestFactory, SimpleTestCase
from django.core.cache import cache
from openpyxl import Workbook, load_workbook
from pypdf import PdfReader

from ColorAdminApp.modules import music_ministry as api
from ColorAdminApp.modules.music_ministry_domain import (roster, history, event_payload, parse_meeting,
                                                        match_person, include_directory, person_matcher, attendance_summary)
from ColorAdminApp.modules.music_ministry_reports import build_pdf, build_excel, event_rows


def fixture():
    catalog = [{'comum': 'BR-22-1 - Central', 'cidade': 'ITAPEVI'},
               {'comum': 'BR-22-2 - Vila', 'cidade': 'COTIA'}]
    registry = [{'id': '1', 'nome_aluno': 'José Silva', 'comum_congregacao': catalog[0]['comum'],
                 'municipio': 'ITAPEVI', 'cargo_ministerio': 'Encarregado Local', 'instrumento': 'VIOLINO', 'status': 'ATIVO'},
                {'id': '2', 'nome_aluno': 'Maria Souza', 'comum_congregacao': catalog[1]['comum'],
                 'municipio': 'COTIA', 'cargo_ministerio': 'Examinadora', 'instrumento': 'ORGAO', 'status': 'ATIVO'}]
    members = [{'id': 'member', 'nome': 'José Silva', 'comum': catalog[0]['comum'], 'cidade': 'ITAPEVI',
                'cargo_outros': 'Encarregado Local', 'status': 'ATIVO'}]
    return catalog, registry, members


def raw_event(**extra):
    return {'titulo': 'Reunião do Ministério da Música', 'tipo': 'REUNIAO_MINISTERIO', 'data_evento': '2026-10-06',
            'modalidade': 'PRESENCIAL', 'local': 'Brás', 'familia': 'GERAL',
            'municipios': ['ITAPEVI', 'COTIA'], 'cargos': ['ENCARREGADO_LOCAL', 'EXAMINADORA'], **extra}


def source_data():
    catalog, registry, members = fixture()
    return {'catalog': catalog, 'registry': registry, 'members': members, 'directory': [],
            'events': [], 'entries': [], 'legacy_events': [], 'legacy_records': [], 'legacy_reviews': [], 'available': True}


class MinistryDomainTests(SimpleTestCase):
    def setUp(self):
        self.catalog, self.registry, self.members = fixture()
        self.people = roster(self.registry, self.members, self.catalog)

    def test_common_with_two_leaders_counts_once_and_preserves_both_people(self):
        rows = [dict(municipio='ITAPEVI', comum='BR-22-1 - Central', present=3, verified=4, pending=0),
                dict(municipio='ITAPEVI', comum='BR-22-1 - Central', present=0, verified=4, pending=0),
                dict(municipio='ITAPEVI', comum='BR-22-2 - Vila', present=0, verified=2, pending=1),
                dict(municipio='COTIA', comum='BR-22-3 - Centro', present=0, verified=4, pending=0)]
        result = attendance_summary(rows)
        self.assertEqual(result['commons'], 3)
        self.assertEqual(result['people'], 4)
        self.assertEqual(result['people_present'], 1)
        self.assertEqual(result['without_presence'], 3)
        self.assertEqual(result['present'], 3)
        self.assertEqual(result['commons_present'], 1)
        self.assertEqual(result['commons_without_presence'], 1)
        self.assertEqual(result['commons_pending'], 1)
        self.assertEqual(sum(result[k] for k in ['commons_present', 'commons_without_presence', 'commons_pending']), result['commons'])

    def test_two_sources_share_one_identity_with_aliases(self):
        self.assertEqual(len(self.people), 2)
        person = next(p for p in self.people if p['nome'] == 'José Silva')
        self.assertEqual(set(person['aliases']), {'sam:1', 'irmandade:member'})
        self.assertEqual(person['families'], ['CORDAS'])

    def test_homonyms_with_two_ids_in_same_source_are_not_merged(self):
        duplicated = [*self.registry, dict(self.registry[0], id='other')]
        people = roster(duplicated, self.members, self.catalog)
        matches = match_person({'nome': 'José Silva', 'comum': self.catalog[0]['comum']}, people)
        self.assertEqual(len(matches), 3)
        self.assertEqual(len(match_person({'sam_pessoa_id': 'other'}, people)), 1)

    def test_indexed_matcher_preserves_homonyms_and_stable_ids(self):
        people = roster([*self.registry, dict(self.registry[0], id='other')], self.members, self.catalog)
        match = person_matcher(people)
        self.assertEqual(len(match({'nome': 'José Silva', 'comum': self.catalog[0]['comum']})), 3)
        self.assertEqual(match({'sam_pessoa_id': 'other'})[0]['key'], 'sam:other')
        self.assertEqual(match({'nome': 'Inexistente', 'comum': self.catalog[0]['comum']}), [])

    def test_planned_event_does_not_create_absences(self):
        result = event_payload(raw_event(), self.people)
        self.assertTrue(all(r['situacao'] == 'SEM_DADOS' for r in result['registros']))

    def test_registered_local_leader_missing_from_import_is_absent(self):
        maria = next(p for p in self.people if p['nome'] == 'Maria Souza')
        source = {'row': 5, 'nome': maria['nome'], 'comum': maria['comum'], 'municipio': maria['municipio'],
                  'roles': maria['roles'], 'source_key': 'importado:1', 'common_resolved': True,
                  'situacao': 'PRESENTE', 'original': {}}
        result = event_payload(raw_event(lista_completa=False), self.people, [source], [{'row': 5, 'key': maria['key']}])
        self.assertEqual(next(r for r in result['registros'] if r['nome'] == 'José Silva')['situacao'], 'SEM_REGISTRO')

    def test_annual_absence_filter_does_not_turn_occasional_absence_into_zero_presence(self):
        events = [dict(id='jan', titulo='January', tipo='ENSAIO_REGIONAL', data_evento='2026-01-18'),
                  dict(id='may', titulo='May', tipo='ENSAIO_REGIONAL', data_evento='2026-05-17')]
        people = roster([*self.registry, dict(self.registry[0], id='second', nome_aluno='Outro encarregado')], self.members, self.catalog)
        records = [dict(evento_id='jan', sam_pessoa_id='1', nome='Present', comum_codigo='BR-22-1', situacao='PRESENTE'),
                   dict(evento_id='may', nome='Unknown', comum_codigo='BR-22-1', situacao='PRESENTE')]
        args = (people, [], [], events, records, self.catalog, {'level': 'regional'})
        annual = history(*args, {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL'})
        absent = history(*args, {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL', 'situacao': 'SEM_REGISTRO'})
        self.assertEqual(absent['summary'], annual['summary'])
        self.assertEqual(absent['summary']['people'], 2)
        self.assertEqual(absent['summary']['people_present'], 1)
        self.assertEqual(absent['summary']['without_presence'], 1)
        self.assertEqual([p['key'] for p in absent['rows']], ['sam:second'])
        may = history(*args, {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL', 'evento': 'legado:may', 'situacao': 'SEM_REGISTRO'})
        self.assertEqual(len(may['rows']), 2)
        self.assertEqual(may['summary']['without_presence'], 2)

    def test_loaded_legacy_list_marks_missing_registered_local_leader_absent(self):
        event = {'id': 'jan', 'titulo': 'Ensaio', 'tipo': 'ENSAIO_REGIONAL', 'data_evento': '2026-01-18'}
        records = [{'evento_id': 'jan', 'nome': 'Outro participante', 'comum_codigo': 'BR-22-1', 'situacao': 'PRESENTE'}]
        result = history(self.people, [], [], [event], records, self.catalog, {'level': 'regional'}, {'ano': 2026})
        jose = next(r for r in result['rows'] if r['nome'] == 'José Silva')
        self.assertEqual(jose['cells'][0]['situacao'], 'SEM_REGISTRO')
        self.assertEqual((jose['present'], jose['verified']), (0, 1))

    def test_local_leader_absence_is_shown_outside_municipal_rotation(self):
        event = dict(id='july', titulo='Ensaio', tipo='ENSAIO_REGIONAL', data_evento='2026-07-19')
        records = [dict(evento_id='july', nome='Outro participante', comum_codigo='BR-22-2', situacao='PRESENTE')]
        args = (self.people, [], [], [event], records, self.catalog, {'level': 'regional'},
                {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL'})
        row = history(*args)['rows'][0]
        self.assertEqual(row['cells'][0]['situacao'], 'SEM_REGISTRO')
        review = dict(event_id='july', person_key=row['key'], nome=row['nome'], comum=row['comum'],
                      municipio=row['municipio'], roles=row['roles'], situacao='PRESENTE',
                      observacoes='Presença confirmada pelo usuário.', version=1)
        corrected = history(*args, [review])['rows'][0]
        self.assertEqual(corrected['cells'][0]['situacao'], 'PRESENTE')
        self.assertEqual(corrected['present'], 1)

    def test_confirmed_role_period_keeps_not_applicable_out_of_absence_totals(self):
        from ColorAdminApp.modules.music_ministry_reports import matrix_table, matrix_events
        person = next(p for p in self.people if p['nome'] == 'José Silva')
        events = [dict(id='july', titulo='Ensaio', tipo='ENSAIO_REGIONAL', data_evento='2026-07-19'),
                  dict(id='sept', titulo='Ensaio', tipo='ENSAIO_REGIONAL', data_evento='2026-09-20')]
        records = [dict(evento_id='july', sam_pessoa_id='1', nome=person['nome'],
                        comum_codigo='BR-22-1', situacao='PRESENTE')]
        review = dict(event_id='sept', person_key=person['key'], nome=person['nome'],
                      comum=person['comum'], municipio=person['municipio'], roles=person['roles'],
                      situacao='NAO_APLICA', observacoes='Não exercia mais o cargo.', version=1)
        data = history(self.people, [], [], events, records, self.catalog, {'level': 'regional'},
                       {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL'}, [review])
        row = data['rows'][0]
        self.assertEqual([c['situacao'] for c in row['cells']], ['PRESENTE', 'NAO_APLICA'])
        self.assertEqual((row['present'], row['verified']), (1, 1))
        self.assertEqual(row['states'].get('SEM_REGISTRO', 0), 0)
        self.assertEqual(matrix_table(data, matrix_events(data))[1][0][-1], 'Não se aplica')

        own_event = dict(id='oct', **raw_event())
        entry = dict(event_id='oct', person_key=person['key'], nome=person['nome'],
                     comum=person['comum'], municipio=person['municipio'], roles=person['roles'],
                     situacao='NAO_APLICA', observacoes='Fora do período do cargo.', source={})
        own = history(self.people, [own_event], [entry], [], [], self.catalog,
                      {'level': 'regional'}, {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL'})
        self.assertEqual(own['rows'][0]['cells'][0]['situacao'], 'NAO_APLICA')
        self.assertEqual(own['rows'][0]['verified'], 0)

    def test_legacy_attendance_is_individual_and_missing_stays_pending(self):
        events = [{'id': 'jan', 'titulo': 'Ensaio', 'tipo': 'ENSAIO_REGIONAL', 'data_evento': '2026-01-18'},
                  {'id': 'may', 'titulo': 'Ensaio', 'tipo': 'ENSAIO_REGIONAL', 'data_evento': '2026-05-17'}]
        records = [{'evento_id': 'jan', 'sam_pessoa_id': '1', 'nome': 'José Silva',
                    'comum_codigo': 'BR-22-1', 'cargo': 'Encarregado Local', 'situacao': 'PRESENTE'}]
        result = history(self.people, [], [], events, records, self.catalog, {'level': 'regional'}, {'ano': 2026})
        jose = next(r for r in result['rows'] if r['nome'] == 'José Silva')
        self.assertEqual((jose['present'], jose['verified'], jose['pending']), (1, 1, 1))
        maria = next(r for r in result['rows'] if r['nome'] == 'Maria Souza')
        self.assertEqual(maria['cells'], [])

    def test_manual_legacy_review_counts_absence_without_overwriting_nominal_presence(self):
        event = {'id': 'jan', 'titulo': 'Ensaio', 'tipo': 'ENSAIO_REGIONAL', 'data_evento': '2026-01-18'}
        key = next(p['key'] for p in self.people if p['nome'] == 'José Silva')
        review = dict(event_id='jan', person_key=key, nome='José Silva', comum=self.catalog[0]['comum'],
                      municipio='ITAPEVI', roles=['ENCARREGADO_LOCAL'], situacao='SEM_REGISTRO', observacoes='Conferido', version=1)
        result = history(self.people, [], [], [event], [], self.catalog, {'level': 'regional'}, {'ano': 2026}, [review])
        row = next(p for p in result['rows'] if p['key'] == key)
        self.assertEqual((row['present'], row['verified']), (0, 1))

    def test_scope_and_city_filters_apply_before_summaries(self):
        result = history(self.people, [], [], [], [], self.catalog,
                         {'level': 'municipal', 'municipio': 'ITAPEVI'}, {'ano': 2026, 'municipios': ['COTIA']})
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['summary']['people'], 0)
        self.assertEqual(result['options']['cities'], ['ITAPEVI'])

    def test_complete_list_and_pending_identity_have_different_denominators(self):
        people = self.people
        source = {'row': 5, 'nome': 'José Silva', 'comum': self.catalog[0]['comum'], 'municipio': 'ITAPEVI',
                  'roles': ['ENCARREGADO_LOCAL'], 'source_key': 'importado:1', 'common_resolved': True,
                  'situacao': 'PRESENTE', 'original': {}}
        key = match_person(source, people)[0]['key']
        result = event_payload(raw_event(lista_completa=True), people, [source], [{'row': 5, 'key': key}])
        self.assertEqual({r['nome']: r['situacao'] for r in result['registros']},
                         {'José Silva': 'PRESENTE', 'Maria Souza': 'SEM_REGISTRO'})
        with self.assertRaises(ValueError):
            event_payload(raw_event(), people, [source], [{'row': 5, 'key': 'sam:2'}])

    def test_rt_family_never_creates_absence_for_another_family(self):
        source = {'row': 5, 'nome': 'José Silva', 'comum': self.catalog[0]['comum'], 'municipio': 'ITAPEVI',
                  'roles': ['ENCARREGADO_LOCAL'], 'source_key': 'importado:1', 'common_resolved': True,
                  'situacao': 'PRESENTE', 'original': {}}
        key = match_person(source, self.people)[0]['key']
        result = event_payload(raw_event(tipo='REUNIAO_TECNICA', familia='CORDAS', lista_completa=True),
                               self.people, [source], [{'row': 5, 'key': key}])
        self.assertEqual(len(result['registros']), 1)

    def test_import_identity_can_be_used_in_following_year(self):
        directory = [{'person_key': 'importado:stable', 'nome': 'Outra pessoa', 'comum': self.catalog[0]['comum'],
                      'municipio': 'ITAPEVI', 'roles': ['ENCARREGADO_LOCAL']}]
        people = include_directory(self.people, directory)
        matches = match_person({'nome': 'Outra pessoa', 'comum': self.catalog[0]['comum']}, people)
        self.assertEqual(matches[0]['key'], 'importado:stable')

    def test_confirmed_alias_uses_registry_name_and_counts_presence_once(self):
        canonical = next(p for p in self.people if p['nome'] == 'José Silva')
        old = {'event_id': 'bras', 'person_key': 'importado:old', 'nome': 'José da Silva',
               'comum': canonical['comum'], 'municipio': canonical['municipio'], 'roles': canonical['roles'],
               'situacao': 'NAO_APLICA', 'observacoes': '', 'source': {'canonical_person_key': canonical['key']}}
        current = {**old, 'person_key': canonical['key'], 'nome': canonical['nome'], 'situacao': 'PRESENTE', 'source': {}}
        directory = [{'person_key': 'importado:old', 'nome': old['nome'], 'comum': old['comum'],
                      'municipio': old['municipio'], 'roles': []}]
        people = include_directory(self.people, directory, [old])
        self.assertEqual(match_person({'nome': old['nome'], 'comum': old['comum']}, people)[0]['key'], canonical['key'])
        event = dict(id='bras', titulo='Reunião no Brás', tipo='REUNIAO_MINISTERIO', data_evento='2026-10-06',
                     local='Brás', modalidade='PRESENCIAL')
        result = history(people, [event], [old, current], [], [], self.catalog, {'level': 'regional'},
                         {'ano': 2026, 'evento': 'bras', 'situacao': 'PRESENTE'})
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['nome'], 'José Silva')
        self.assertEqual(result['rows'][0]['present'], 1)
        self.assertNotIn('importado:old', [p['key'] for p in result['rows']])

    def workbook(self, formula=False):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['REUNIÃO DE 06/10/2026'])
        sheet.append(['Nome', 'Ministério/Cargo', 'Localidade', 'Cidade', 'Presença'])
        sheet.append(['=1+1' if formula else 'José Silva', 'Encarregado Local', 'BR-22-1 - Central', 'ITAPEVI', 'Sim'])
        stream = BytesIO()
        workbook.save(stream)
        return stream.getvalue()

    def test_parser_reads_header_date_and_canonical_common(self):
        result = parse_meeting(self.workbook(), self.catalog)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['suggested_date'], '2026-10-06')
        self.assertTrue(result['records'][0]['common_resolved'])

    def test_parser_rejects_formula_cells(self):
        with self.assertRaisesRegex(ValueError, 'fórmulas'):
            parse_meeting(self.workbook(True), self.catalog)


class MinistryApiTests(SimpleTestCase):
    @patch.object(api.music_events, '_allowed', return_value=True)
    @patch.object(api, '_sources')
    @patch.object(api, '_rpc', return_value={'id': 'bras'})
    def test_reimport_preserves_event_exclusion(self, rpc, sources, _):
        data = source_data()
        data['events'] = [dict(id='bras', **raw_event())]
        person = roster(data['registry'], data['members'], data['catalog'])[0]
        data['entries'] = [dict(event_id='bras', person_key=person['key'], nome=person['nome'],
            comum=person['comum'], municipio=person['municipio'], roles=person['roles'],
            situacao='NAO_APLICA', observacoes='Não exercia o cargo neste encontro.', source={}, version=3)]
        sources.return_value = data
        cache.set('music-ministry:preview:operator:exclusion-test',
                  {'records': [], 'sha256': 'a' * 64, 'filename': 'lista.xlsx'}, 1800)
        request = self.factory.post('/', json.dumps(raw_event(conferido=True, event_id='bras', token='exclusion-test')),
                                    content_type='application/json')
        request.session = self.request().session
        response = api.api_manage(request, 'salvar')
        self.assertEqual(response.status_code, 200)
        saved = rpc.call_args.args[1]['p_evento']['registros']
        self.assertEqual(saved[0]['situacao'], 'NAO_APLICA')
        self.assertEqual(saved[0]['observacoes'], data['entries'][0]['observacoes'])

    def setUp(self):
        self.factory = RequestFactory()
        cache.clear()

    def request(self, url='/', data=None):
        request = self.factory.get(url, data or {})
        request.session = {'authenticated': True, 'user_id': 'operator',
                           'user_profile': {'full_name': 'Operador', 'nome': 'Operador',
                                            'name': 'Operador', 'role_id': 1}}
        return request

    @patch.object(api, '_sources', return_value=source_data())
    def test_common_conductor_statuses_are_merged_and_scoped(self, sources):
        sources.return_value = {**source_data(),
            'legacy_frequency': [
                {'evento_id': 'regional', 'comum_codigo': 'BR-22-1', 'comum': 'Central',
                 'municipio': 'ITAPEVI', 'encarregado_situacao': 'ENFERMO'},
                {'evento_id': 'regional', 'comum_codigo': 'BR-22-2', 'comum': 'Vila',
                 'municipio': 'COTIA', 'encarregado_situacao': 'NAO_INFORMADO'}],
            'legacy_conductor_reviews': [
                {'evento_id': 'regional', 'comum_chave': 'BR-22-1', 'comum_nome': 'Central',
                 'municipio': 'ITAPEVI', 'situacao': 'NAO_JUSTIFICOU'}]}
        result = api.dashboard_data(self.request())
        statuses = result['legacy_conductor_statuses']
        self.assertEqual({row['comum_codigo']: row['situacao'] for row in statuses},
                         {'BR-22-1': 'NAO_JUSTIFICOU', 'BR-22-2': 'NAO_INFORMADO'})
        self.assertEqual(next(row for row in statuses if row['comum_codigo'] == 'BR-22-1')['comum'],
                         'BR-22-1 - Central')

        request = self.request()
        request.session['user_profile'] = {'role_id': 3, 'municipio': 'COTIA'}
        scoped = api.dashboard_data(request)
        self.assertEqual({row['comum_codigo'] for row in scoped['legacy_conductor_statuses']},
                         {'BR-22-2'})

    @patch.object(api.music_events, '_allowed', return_value=False)
    def test_read_and_export_require_authorization(self, _):
        self.assertEqual(api.api_dashboard(self.request()).status_code, 403)
        self.assertEqual(api.export(self.request(), 'pdf').status_code, 403)

    @patch.object(api.music_events, '_allowed', return_value=True)
    @patch.object(api, 'user_scope', return_value={'level': 'local', 'comum': 'BR-22-1 - Central', 'municipio': 'ITAPEVI'})
    def test_local_user_cannot_write(self, *_):
        request = self.factory.post('/', '{}', content_type='application/json')
        request.session = self.request().session
        self.assertEqual(api.api_manage(request, 'salvar').status_code, 403)

    @patch.object(api, '_sources', return_value=source_data())
    def test_filters_are_shared_with_exports(self, sources):
        sources.return_value = {**source_data(),
            'events': [dict(id='meeting', titulo='Reunião', tipo='REUNIAO_MINISTERIO', data_evento='2026-10-06', local='Brás', modalidade='PRESENCIAL')],
            'entries': [dict(event_id='meeting', person_key='sam:2', nome='Maria Souza',
                comum=fixture()[0][1]['comum'], municipio='COTIA', roles=['EXAMINADORA'],
                situacao='PRESENTE', observacoes='', source={})]}
        data = api.dashboard_data(self.request(data={'municipio': ['COTIA'], 'cargo': ''}))
        self.assertEqual(data['selected_cities'], ['COTIA'])
        self.assertEqual(data['summary']['people'], 1)
        pdf = PdfReader(BytesIO(build_pdf(data, 'Teste', datetime(2026,11,3,12,30))))
        text = '\n'.join(page.extract_text() for page in pdf.pages)
        self.assertIn('CONGREGAÇÃO CRISTÃ NO BRASIL', text)
        self.assertIn('Maria Souza', text)
        self.assertNotIn('José Silva', text)
        self.assertIn('03/11/2026 12:30', text)
        excel = load_workbook(BytesIO(build_excel(data, 'Teste', datetime(2026,11,3,12,30))))
        self.assertEqual(excel.sheetnames, ['Acompanhamento'])
        self.assertEqual(excel['Acompanhamento']['A1'].value, 'CONGREGAÇÃO CRISTÃ NO BRASIL')
        self.assertEqual(excel['Acompanhamento']['B8'].value, 'Maria Souza')
        self.assertEqual(excel['Acompanhamento'].freeze_panes, 'E8')
        for sheet in excel:
            self.assertFalse(sheet.sheet_view.showGridLines)
            self.assertEqual(sheet.page_setup.fitToWidth, 1)
            self.assertEqual(sheet['A7'].fill.fgColor.rgb, '001E4B7A')

    @patch.object(api, '_sources', return_value=source_data())
    def test_annual_exports_use_one_row_per_person_and_match_event_statuses(self, sources):
        from ColorAdminApp.modules.music_ministry_reports import matrix_table, matrix_events
        sources.return_value = {**source_data(), 'events': [
            dict(id='meeting', titulo='Reunião', tipo='REUNIAO_MINISTERIO', data_evento='2026-10-06',
                 local='Brás', modalidade='PRESENCIAL'),
            dict(id='second', titulo='Ensaio', tipo='ENSAIO_REGIONAL', data_evento='2026-11-01',
                 local='Itapevi', modalidade='PRESENCIAL')], 'entries': [
            dict(event_id=key, person_key='sam:1', nome='José Silva', comum=fixture()[0][0]['comum'],
                 municipio='ITAPEVI', roles=['ENCARREGADO_LOCAL'], situacao=state, observacoes='', source={})
            for key, state in [('meeting', 'PRESENTE'), ('second', 'SEM_REGISTRO')]]}
        data = api.dashboard_data(self.request(data={'municipio': ['ITAPEVI']}))
        events = matrix_events(data)
        labels, rows = matrix_table(data, events)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][4:], ['Presente', 'Não participou'])
        self.assertIn('06/10/2026', labels[4])
        workbook = load_workbook(BytesIO(build_excel(data, 'Teste', datetime(2026, 11, 12, 13, 0))))
        sheet = workbook.active
        self.assertEqual(sheet.max_row, 8)
        self.assertEqual([sheet.cell(8, col).value for col in (5, 6)], rows[0][4:])
        self.assertEqual(sheet['F8'].font.color.rgb, '00B4233D')
        pdf = PdfReader(BytesIO(build_pdf(data, 'Teste', datetime(2026, 11, 12, 13, 0))))
        text = '\n'.join(page.extract_text() for page in pdf.pages)
        self.assertEqual(text.count('José Silva'), 1)
        self.assertNotIn('Histórico por pessoa e evento', text)
        self.assertIn('06/10/2026', text)
        missing = {**data, 'rows': [{**data['rows'][0], 'cells': data['rows'][0]['cells'][:1]}]}
        self.assertEqual(matrix_table(missing, events)[1][0][-1], 'Não participou')
        self.assertIn('Secretaria Regional da Música', text)
        self.assertIn('Impresso por:', text)
        self.assertEqual(sheet.oddFooter.right.text, '&BImpresso por:&B Teste')

    @patch.object(api, '_sources', return_value=source_data())
    def test_page_renders_export_toolbar(self, _):
        with patch.object(api.music_events, '_allowed', return_value=True):
            response = api.page(self.request())
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'ministry-pdf', response.content)
        self.assertIn(b'ministry-city', response.content)

    @patch.object(api.music_events, '_allowed', return_value=True)
    @patch.object(api, '_sources', return_value=source_data())
    @patch.object(api, '_rpc', return_value={'id': 'event', 'existing': False})
    def test_planned_meeting_is_saved_with_no_data_states(self, rpc, sources, *_):
        data = source_data()
        data['transitions'] = [dict(aluno_id='1', campo=field, anterior=None, posterior=value,
            effective_at='2026-01-01', date_basis='sam', source_ref='test:' + field)
            for field, value in [('cargo_ministerio', 'Encarregado Local'),
                ('comum_congregacao', fixture()[0][0]['comum']), ('municipio', 'ITAPEVI')]]
        sources.return_value = data
        raw = raw_event(conferido=True)
        request = self.factory.post('/', json.dumps(raw), content_type='application/json')
        request.session = self.request().session
        response = api.api_manage(request, 'salvar')
        self.assertEqual(response.status_code, 200)
        saved = rpc.call_args.args[1]['p_evento']
        self.assertTrue(all(row['situacao'] == 'SEM_DADOS' for row in saved['registros']))

    @patch.object(api.music_events, '_allowed', return_value=True)
    @patch.object(api, '_sources', return_value=source_data())
    @patch.object(api, '_rpc')
    def test_complete_list_without_a_preview_cannot_create_absences(self, rpc, *_):
        request = self.factory.post('/', json.dumps(raw_event(conferido=True, lista_completa=True)), content_type='application/json')
        request.session = self.request().session
        response = api.api_manage(request, 'salvar')
        self.assertEqual(response.status_code, 400)
        rpc.assert_not_called()

    @patch.object(api.music_events, '_allowed', return_value=True)
    @patch.object(api, '_sources', return_value=source_data())
    @patch.object(api, '_rpc')
    def test_preview_token_cannot_be_used_by_another_operator(self, rpc, *_):
        cache.set('music-ministry:preview:another:secret-token', {'records': []}, 1800)
        request = self.factory.post('/', json.dumps(raw_event(conferido=True, token='secret-token')), content_type='application/json')
        request.session = self.request().session
        self.assertEqual(api.api_manage(request, 'salvar').status_code, 400)
        rpc.assert_not_called()

    @patch.object(api.music_events, '_allowed', return_value=True)
    def test_bras_present_export_is_a_filtered_nominal_list(self, _):
        sources = source_data()
        event = dict(id='bras', titulo='Reunião do Ministério da Música', tipo='REUNIAO_MINISTERIO',
                     data_evento='2026-10-06', modalidade='PRESENCIAL', local='Brás')
        sources['events'] = [event]
        people = roster(sources['registry'], sources['members'], sources['catalog'])
        sources['entries'] = [dict(event_id='bras', person_key=p['key'], nome=p['nome'], comum=p['comum'],
            municipio=p['municipio'], roles=p['roles'], situacao='PRESENTE' if p['nome'] == 'José Silva' else 'SEM_REGISTRO',
            observacoes='', version=1) for p in people]
        request = self.request(data={'evento': 'bras', 'situacao': 'PRESENTE', 'cargo': ''})
        with patch.object(api, '_sources', return_value=sources):
            data = api.dashboard_data(request)
            pdf = api.export(request, 'pdf')
            excel = api.export(request, 'excel')
        self.assertEqual([p['nome'] for p in data['rows']], ['José Silva'])
        self.assertEqual(data['event_options'][0]['id'], 'bras')
        self.assertIn('REUNIÃO_MUSICAL_BRÁS_06_10_2026.pdf', pdf['Content-Disposition'])
        text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
        self.assertIn('Lista de presentes', text)
        self.assertIn('06/10/2026', text)
        self.assertIn('JOSÉ SILVA', text)
        self.assertNotIn('MARIA SOUZA', text)
        workbook = load_workbook(BytesIO(excel.content))
        self.assertEqual(workbook.sheetnames, ['Presenças'])
        self.assertEqual(workbook.active['B8'].value, 'JOSÉ SILVA')
        self.assertEqual(workbook.active.max_row, 8)

    def test_regional_event_report_includes_common_statuses_and_centers_situation(self):
        event_id = 'legado:ensaio'
        data = {
            'year': 2026,
            'selected_cities': ['ITAPEVI', 'COTIA'],
            'filters': {'evento': event_id, 'cargo': '', 'tipo': '', 'situacao': '',
                        'municipios': [], 'comuns': [], 'busca': ''},
            'event_options': [{'id': event_id, 'date': '2026-07-19',
                               'titulo': 'Ensaio Regional', 'tipo': 'ENSAIO_REGIONAL'}],
            'rows': [
                {'nome': 'José Silva', 'municipio': 'ITAPEVI', 'comum': 'BR-22-1 - Central',
                 'roles': ['ENCARREGADO_LOCAL'], 'cells': [
                     {'event_id': event_id, 'situacao': 'SEM_REGISTRO',
                      'roles': ['ENCARREGADO_LOCAL'], 'comum': 'BR-22-1 - Central'}]},
                {'nome': 'Maria Souza', 'municipio': 'COTIA', 'comum': 'BR-22-2 - Vila',
                 'roles': ['EXAMINADORA'], 'cells': [
                     {'event_id': event_id, 'situacao': 'SEM_REGISTRO',
                      'roles': ['EXAMINADORA'], 'comum': 'BR-22-2 - Vila'}]},
                {'nome': 'Ana Lima', 'municipio': 'ITAPEVI', 'comum': 'BR-22-3 - Centro',
                 'roles': ['EXAMINADORA'], 'cells': [
                     {'event_id': event_id, 'situacao': 'JUSTIFICOU',
                      'roles': ['EXAMINADORA'], 'comum': 'BR-22-3 - Centro'}]},
                {'nome': 'Paulo Reis', 'municipio': 'ITAPEVI', 'comum': 'BR-22-7 - Parque',
                 'roles': ['ENCARREGADO_LOCAL'], 'cells': [
                     {'event_id': event_id, 'situacao': 'PRESENTE',
                      'roles': ['ENCARREGADO_LOCAL'], 'comum': 'BR-22-7 - Parque'}]},
            ],
            'legacy_conductor_statuses': [
                {'event_id': 'ensaio', 'comum_codigo': 'BR-22-1', 'comum': 'BR-22-1 - Central',
                 'municipio': 'ITAPEVI', 'situacao': 'ENFERMO'},
                {'event_id': 'ensaio', 'comum_codigo': 'BR-22-2', 'comum': 'BR-22-2 - Vila',
                 'municipio': 'COTIA', 'situacao': 'SEM_ENCARREGADO'},
                {'event_id': 'ensaio', 'comum_codigo': 'BR-22-4', 'comum': 'BR-22-4 - Centro',
                 'municipio': 'ITAPEVI', 'situacao': 'NAO_JUSTIFICOU'},
                {'event_id': 'ensaio', 'comum_codigo': 'BR-22-5', 'comum': 'BR-22-5 - Vila',
                 'municipio': 'COTIA', 'situacao': 'NAO_INFORMADO'},
                {'event_id': 'ensaio', 'comum_codigo': 'BR-22-6', 'comum': 'BR-22-6 - Parque',
                 'municipio': 'ITAPEVI', 'situacao': 'JUSTIFICOU'},
                {'event_id': 'ensaio', 'comum_codigo': 'BR-22-7', 'comum': 'BR-22-7 - Parque',
                 'municipio': 'ITAPEVI', 'situacao': 'PRESENTE'},
            ],
        }
        rows = event_rows(data)
        labels = {row[4] for row in rows}
        self.assertTrue({'Presente', 'Justificou', 'Não participou', 'Não justificou',
                         'Sem encarregado', 'Enfermo', 'Não informado'} <= labels)
        self.assertIn('JOSÉ SILVA', {row[1] for row in rows})
        self.assertTrue(all(row[1] == row[1].upper() for row in rows))

        workbook = load_workbook(BytesIO(build_excel(data, 'Teste', datetime(2026, 11, 12, 13, 0))))
        self.assertEqual(workbook.sheetnames, ['Participação'])
        self.assertIn('JOSÉ SILVA', [workbook.active.cell(row, 2).value
                                    for row in range(8, workbook.active.max_row + 1)])
        self.assertEqual(workbook.active['E8'].alignment.horizontal, 'center')
        pdf = PdfReader(BytesIO(build_pdf(data, 'Teste', datetime(2026, 11, 12, 13, 0))))
        text = '\n'.join(page.extract_text() for page in pdf.pages)
        for label in ('Presente', 'Justificou', 'Não participou', 'Não justificou',
                      'Sem encarregado', 'Enfermo', 'Não informado'):
            self.assertIn(label, text)
        self.assertIn('JOSÉ SILVA', text)

    @patch.object(api, '_sources', return_value=source_data())
    def test_invalid_state_filter_is_rejected(self, _):
        with self.assertRaises(ValueError):
            api.dashboard_data(self.request(data={'situacao': 'INVALIDA'}))
