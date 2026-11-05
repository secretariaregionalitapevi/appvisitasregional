from datetime import datetime
from io import BytesIO

from django.test import SimpleTestCase
from openpyxl import load_workbook
from pypdf import PdfReader

from ColorAdminApp.modules.sam_temporal import state_at, temporal_roster, transitions_from_audit
from ColorAdminApp.modules.music_ministry_domain import history, event_payload
from ColorAdminApp.modules.music_ministry_reports import build_excel, build_pdf
from ColorAdminApp.modules.gem import _build_timeline


COMMON = 'BR-22-3129 - PARQUE SUBURBANO III'
CENTRAL = 'BR-22-1 - CENTRAL'


def transition(identity, field, before, after, day='2026-09-01', basis='sam'):
    return dict(aluno_id=identity, campo=field, anterior=before, posterior=after,
                effective_at=day, detected_at='2026-11-04T12:00:00Z', date_basis=basis,
                source_ref=f'{identity}:{field}:{day}')


class TemporalTests(SimpleTestCase):
    def test_event_exclusion_does_not_count_absence_or_remove_previous_history(self):
        catalog, people, legacy = self.setup_data()
        events = [{**e, 'local': 'Brás', 'modalidade': 'PRESENCIAL'} for e in legacy]
        entries = [dict(event_id=e['id'], person_key='sam:h', nome='Henrique', comum=COMMON,
                        municipio='ITAPEVI', roles=['ENCARREGADO_LOCAL'], source={},
                        situacao=state, observacoes='', version=1)
                   for e, state in zip(events, ['SEM_REGISTRO', 'NAO_APLICA'])]
        result = history(people, events, entries, [], [], catalog, {'level': 'regional'},
                         {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL', 'situacao': 'SEM_REGISTRO'})
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual([c['event_id'] for c in result['rows'][0]['cells']], ['jan'])
        result = history(people, events, entries, [], [], catalog, {'level': 'regional'},
                         {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL', 'situacao': 'SEM_REGISTRO', 'evento': 'bras'})
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['summary']['people'], 0)

    def setup_data(self):
        catalog = [{'comum': COMMON, 'cidade': 'ITAPEVI'}, {'comum': CENTRAL, 'cidade': 'ITAPEVI'}]
        registry = [dict(id='h', nome_aluno='Henrique', cargo_ministerio='Músico',
                         comum_congregacao=CENTRAL, municipio='ITAPEVI', status='Ativo'),
                    dict(id='j', nome_aluno='Jeferson', cargo_ministerio='Encarregado Local',
                         comum_congregacao=COMMON, municipio='ITAPEVI', status='Ativo')]
        changes = []
        for identity, before, after, first_common, last_common in [
            ('h', 'Encarregado Local', 'Músico', COMMON, CENTRAL),
            ('j', 'Músico', 'Encarregado Local', CENTRAL, COMMON)]:
            changes.extend([transition(identity, 'cargo_ministerio', before, after),
                            transition(identity, 'comum_congregacao', first_common, last_common),
                            transition(identity, 'municipio', 'COTIA', 'ITAPEVI', '2025-01-01')])
        people = temporal_roster(registry, [], catalog, changes)
        events = [dict(id='jan', titulo='Ensaio janeiro', tipo='ENSAIO_REGIONAL', data_evento='2026-01-18'),
                  dict(id='bras', titulo='Reunião Brás', tipo='REUNIAO_TECNICA', data_evento='2026-10-06')]
        return catalog, people, events

    def test_counts_use_role_and_common_at_each_event_even_after_current_role_changed(self):
        catalog, people, events = self.setup_data()
        records = [dict(evento_id=event['id'], sam_pessoa_id=identity, nome=name,
                        comum_informada=common, municipio_informado='ITAPEVI', cargo=role, situacao='PRESENTE')
                   for event, identity, name, common, role in [
                       (events[0], 'h', 'Henrique', COMMON, 'Encarregado Local'),
                       (events[0], 'j', 'Jeferson', CENTRAL, 'Músico'),
                       (events[1], 'h', 'Henrique', CENTRAL, 'Músico'),
                       (events[1], 'j', 'Jeferson', COMMON, 'Encarregado Local')]]
        for event, expected in [('jan', 'Henrique'), ('bras', 'Jeferson')]:
            filters = {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL', 'evento': 'legado:' + event}
            result = history(people, [], [], events, records, catalog, {'level': 'regional'}, filters)
            self.assertEqual([p['nome'] for p in result['rows']], [expected])
            self.assertEqual(result['rows'][0]['cells'][0]['comum'], COMMON)
            self.assertEqual(result['summary']['present'], 1)
            result['filters'] = filters
            pdf = PdfReader(BytesIO(build_pdf(result, 'Operador', datetime(2026, 11, 4, 12))))
            self.assertIn(expected, '\n'.join(p.extract_text() for p in pdf.pages))
            book = load_workbook(BytesIO(build_excel(result, 'Operador', datetime(2026, 11, 4, 12))))
            self.assertTrue(any(expected == cell.value for sheet in book for row in sheet for cell in row))

    def test_effective_dates_determine_expected_roster_without_nominal_snapshots(self):
        catalog, people, events = self.setup_data()
        # Loaded list contains another participant; both absences use dated roles.
        records = [dict(evento_id=e['id'], nome='Outro', comum_informada=COMMON,
                        municipio_informado='ITAPEVI', situacao='PRESENTE') for e in events]
        result = history(people, [], [], events, records, catalog, {'level': 'regional'},
                         {'ano': 2026, 'cargo': 'ENCARREGADO_LOCAL'})
        self.assertEqual({p['nome']: [c['event_id'] for c in p['cells']] for p in result['rows']},
                         {'Henrique': ['legado:jan'], 'Jeferson': ['legado:bras']})

    def test_detection_does_not_backdate_role(self):
        changes = [transition('j', 'cargo_ministerio', 'Músico', 'Encarregado Local', basis='detected_at_sync')]
        result = state_at({'cargo_ministerio': 'Encarregado Local'}, changes, '2026-01-18')
        self.assertIsNone(result['cargo_ministerio'])
        self.assertIn('cargo_ministerio', result['_unknown'])

    def test_all_academic_levels_and_ingress_keep_their_own_dates(self):
        changes = [transition('o', 'nivel', 'CANDIDATO(A)', 'RJM', '2024-03-10'),
                   transition('o', 'nivel', 'RJM', 'CULTO OFICIAL', '2025-04-20'),
                   transition('o', 'nivel', 'CULTO OFICIAL', 'OFICIALIZADO(A)', '2026-08-02'),
                   transition('o', 'data_inicio_gem', None, '2023-02-01', '2023-02-01')]
        for day, expected in [('2024-01-01', 'CANDIDATO(A)'), ('2024-03-10', 'RJM'),
                              ('2025-05-01', 'CULTO OFICIAL'), ('2026-08-02', 'OFICIALIZADO(A)')]:
            self.assertEqual(state_at({}, changes, day)['nivel'], expected)
        self.assertEqual(state_at({}, changes, '2026-11-04')['data_inicio_gem'], '2023-02-01')
        timeline = _build_timeline({}, {'transicoes': changes})
        self.assertEqual(len(timeline), 4)
        self.assertEqual({r['date'][:10] for r in timeline}, {'2024-03-10', '2025-04-20', '2026-08-02', '2023-02-01'})

    def test_generic_save_log_is_not_evidence_of_role_change(self):
        event = dict(occurred_at='2026-09-01T12:00:00', source_fingerprint='abc',
                     parsed_refs={'student_id': 123}, source_payload={'action': 'Salvou aluno: 123'})
        self.assertEqual(transitions_from_audit(event), [])
        event['source_payload'].update(before={'nivel': 'RJM'}, after={'nivel': 'CULTO OFICIAL'})
        payload = transitions_from_audit(event)[0]
        self.assertEqual(payload['p_source_key'], '123')
        self.assertEqual(payload['p_effective_at'], '2026-09-01T12:00:00-03:00')

    def test_conductor_conference_does_not_promote_january_musician_using_current_role(self):
        from ColorAdminApp.modules.music_events_conductors import summarize
        catalog, people, events = self.setup_data()
        registry = [p['current_state'] for p in people]
        transitions = [r for p in people for r in p['transitions']]
        records = [dict(evento_id=e['id'], local_id=e['id'], nome='Jeferson',
                        comum_informada=COMMON, municipio_informado='ITAPEVI', cargo='MÚSICO') for e in events]
        sites = [dict(id=e['id'], evento_id=e['id'], nome='ITAPEVI', municipio='ITAPEVI') for e in events]
        data = summarize(events, records, sites, [], {'origem': 'regional'}, catalog,
                         leaders=registry, transitions=transitions)
        states = {row['evento_id']: row['situacao'] for row in data['rows']}
        self.assertEqual(states['jan'], 'NAO_INFORMADO')
        self.assertEqual(states['bras'], 'PRESENTE')
