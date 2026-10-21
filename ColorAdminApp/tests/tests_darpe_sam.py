import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from django.urls import resolve

from ColorAdminApp.modules.darpe_sam import api, enrich_roles, fill_confirmed, filtered, page, reconcile, standardize_spellings
from ColorAdminApp.tests.tests_darpe import request_for


CATALOG = [
    {'comum': 'BR-22-0673 - VILA DOUTOR CARDOSO', 'cidade': 'ITAPEVI'},
    {'comum': 'BR-22-3061 - JARDIM RUTH', 'cidade': 'ITAPEVI'},
]
SCOPE = {'level': 'regional', 'municipio': '', 'comum': ''}


def target(**changes):
    return {'id': '11111111-1111-4111-8111-111111111111', 'nome_completo': 'Ricardo de Castro Grangeiro',
            'comum_congregacao': CATALOG[0]['comum'], 'cidade': 'ITAPEVI', 'status': 'ATIVO',
            'instrumento_oficializado': None, 'darpe_musico': True, 'updated_at': '2026-10-21T10:00:00+00:00', **changes}


def source(**changes):
    return {'id': 'sam-1', 'source_name': 'RICARDO DE CASTRO GRANGEIRO', 'source_common': CATALOG[0]['comum'],
            'source_instrument': 'VIOLINO', 'source_level': 'OFICIALIZADO(A)',
            'source_payload': {'city': 'Itapevi'}, 'last_seen_at': '2026-10-21T10:00:00Z', **changes}


class DarpeSamTests(SimpleTestCase):
    def compare(self, targets=None, sources=None, scope=None):
        return reconcile([target()] if targets is None else targets,
                         [source()] if sources is None else sources, CATALOG, scope or SCOPE)[0]

    def test_exact_unique_name_and_common_allows_fill(self):
        rows = self.compare()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['situacao'], 'preencher')
        self.assertEqual(rows[0]['sam_instrumento'], 'VIOLINO')

    def test_common_alias_and_name_accents_are_normalized(self):
        rows = self.compare([target(nome_completo='  Rícardo de Castro Grangeiro ', comum_congregacao='VL DR CARDOSO - ITAPEVI')])
        self.assertEqual(rows[0]['situacao'], 'preencher')

    def test_different_instrument_is_only_flagged(self):
        rows = self.compare([target(instrumento_oficializado='VIOLONCELO')])
        self.assertEqual(rows[0]['situacao'], 'divergente')
        self.assertEqual(rows[0]['darpe_instrumento'], 'VIOLONCELO')

    def test_instrument_aliases_do_not_create_false_divergences(self):
        rows = self.compare([target(instrumento_oficializado='FLAUTA TRANSVERSAL')], [source(source_instrument='FLAUTA')])
        self.assertEqual(rows[0]['situacao'], 'conferido')

    @patch('ColorAdminApp.modules.darpe_sam.requests.patch')
    def test_violoncello_is_equivalent_and_adopts_sam_spelling(self, update):
        rows = self.compare([target(instrumento_oficializado='Violoncello')], [source(source_instrument='VIOLONCELO')])
        self.assertEqual(rows[0]['situacao'], 'conferido')
        update.return_value.json.return_value = [{'id': target()['id']}]
        self.assertEqual(standardize_spellings(rows, {'id': 'actor', 'name': 'Operador'}), 1)
        saved = update.call_args.kwargs
        self.assertEqual(saved['json']['instrumento_oficializado'], 'VIOLONCELO')
        self.assertEqual(saved['params']['instrumento_oficializado'], 'eq.Violoncello')
        self.assertIn('updated_at', saved['params'])

    @patch('ColorAdminApp.modules.darpe_sam.requests.patch')
    def test_spelling_standardization_never_replaces_a_different_instrument(self, update):
        rows = self.compare([target(instrumento_oficializado='VIOLINO')], [source(source_instrument='VIOLONCELO')])
        self.assertEqual(rows[0]['situacao'], 'divergente')
        self.assertEqual(standardize_spellings(rows, {'id': 'actor', 'name': 'Operador'}), 0)
        update.assert_not_called()

    def test_name_alone_and_abbreviations_never_allow_fill(self):
        self.assertEqual(self.compare([target(comum_congregacao=CATALOG[1]['comum'])])[0]['situacao'], 'ambiguo')
        rows = self.compare([target(nome_completo='RICARDO C GRANGEIRO')])
        self.assertIn(next(r for r in rows if r['darpe_id'])['situacao'], {'sem_sam', 'nome_divergente'})
        self.assertIsNone(next(r for r in rows if r['darpe_id'])['sam_id'])

    def test_particle_difference_is_review_not_missing_and_never_auto_filled(self):
        rows = self.compare([target(nome_completo='RICARDO CASTRO GRANGEIRO')])
        self.assertEqual(rows[0]['situacao'], 'nome_divergente')
        self.assertEqual(rows[0]['sam_nome'], 'RICARDO DE CASTRO GRANGEIRO')
        self.assertIsNone(rows[0]['sam_id'])
        self.assertEqual(fill_confirmed(rows, {'id': 'actor', 'name': 'Operador'}), 0)

    def test_explicitly_confirmed_daniel_matches_same_common_and_local_role(self):
        catalog = [{'comum': 'BR-21-1020 - NHAMBUCA', 'cidade': 'CAUCAIA DO ALTO'}]
        d = target(nome_completo='DANIEL LUIZ DA SILVA SANTOS', comum_congregacao=catalog[0]['comum'], cidade='CAUCAIA DO ALTO')
        s = source(source_name='DANIEL LUIZ DA SILVA DOS SANTOS', source_common=catalog[0]['comum'],
                   source_instrument='SAXOFONE ALTO', source_ministry='ENCARREGADO LOCAL')
        rows = reconcile([d], [s], catalog, SCOPE)[0]
        self.assertEqual(rows[0]['situacao'], 'preencher')
        self.assertEqual(rows[0]['encarregado_tipo'], 'LOCAL')
        other = {**d, 'id': 'duplicate', 'nome_completo': s['source_name']}
        rows = reconcile([d, other], [s], catalog, SCOPE)[0]
        self.assertTrue(all(row['sam_id'] is None for row in rows))

    def test_regional_role_is_never_classified_as_local(self):
        rows = self.compare(sources=[source(source_ministry='ENCARREGADO REGIONAL')])
        self.assertEqual(rows[0]['encarregado_tipo'], 'REGIONAL')

    @patch('ColorAdminApp.modules.darpe_sam.cache.get', return_value=None)
    @patch('ColorAdminApp.modules.darpe_sam._read_all_rows')
    def test_cadastro_roles_are_read_from_sam_without_guessing_scope(self, read, _cache):
        read.return_value = [{'id': 'sam', 'nome_aluno': target()['nome_completo'],
                              'comum_congregacao': CATALOG[0]['comum'], 'cargo_ministerio': 'ENCARREGADO REGIONAL'}]
        rows = enrich_roles([target(darpe_encarregado=True)])
        self.assertEqual(rows[0]['encarregado_tipo'], 'REGIONAL')
        read.return_value[0]['cargo_ministerio'] = 'ENCARREGADO LOCAL'
        self.assertEqual(enrich_roles([target(darpe_encarregado=True)])[0]['encarregado_tipo'], 'LOCAL')

    def test_missing_from_sam_never_reappears_from_older_local_catalog(self):
        rows = self.compare(sources=[source(missing_since='2026-10-20', aluno_id='local'),
                                     source(id='local', source_kind='sam_gem')])
        self.assertEqual(rows[0]['situacao'], 'sem_sam')

    def test_ministerial_without_musical_function_is_not_a_missing_sam(self):
        rows = self.compare([target(darpe_ministerio=True, darpe_musico=False)], sources=[])
        self.assertEqual(rows[0]['situacao'], 'ministerio')
        self.assertEqual(rows[0]['correspondencia'], 'Não se aplica')
        rows = self.compare([target(darpe_ministerio=True, darpe_musico=True)], sources=[])
        self.assertEqual(rows[0]['situacao'], 'sem_sam')

    def test_only_non_musical_roles_are_exempt_even_when_sam_match_exists(self):
        for roles in ({'darpe_atendente': True}, {'darpe_colaborador': True},
                      {'darpe_encarregado': True}, {'darpe_grupo_canto': True},
                      {'darpe_atendente': True, 'darpe_colaborador': True}, {}):
            with self.subTest(roles=roles):
                rows = self.compare([target(darpe_musico=False, **roles)])
                row = rows[0]
                self.assertEqual(row['situacao'], 'sem_funcao_musical')
                self.assertEqual(row['correspondencia'], 'Não se aplica')
                self.assertIsNone(row['sam_id'])
                self.assertEqual(row['sam_instrumento'], '')
                self.assertEqual(row['candidatos'], [])
                self.assertEqual(fill_confirmed(rows, {'id': 'actor', 'name': 'Operador'}), 0)

    def test_attendant_musician_or_organist_requires_officialization(self):
        for roles in ({'darpe_musico': True}, {'darpe_musico': False, 'darpe_organista': True},
                      {'darpe_musico': False, 'darpe_musico_organista': True}):
            with self.subTest(roles=roles):
                row = target(darpe_atendente=True, **roles)
                self.assertEqual(self.compare([row], sources=[])[0]['situacao'], 'sem_sam')
                self.assertEqual(self.compare([row], [source(source_level='CULTO OFICIAL')])[0]['situacao'], 'nao_oficializado')
                self.assertEqual(self.compare([row])[0]['situacao'], 'preencher')

    def test_instrument_value_alone_does_not_define_musical_role(self):
        rows = self.compare([target(darpe_musico=False, darpe_atendente=True, instrumento_oficializado='VIOLINO')])
        self.assertEqual(rows[0]['situacao'], 'sem_funcao_musical')

    def test_similar_names_are_not_automatically_linked(self):
        rows = self.compare([target(nome_completo='RAFAELA JALES DA SILVA')],
                            [source(source_name='RAFAEL JALES DA SILVA')])
        self.assertEqual(rows[0]['situacao'], 'nome_divergente')
        self.assertIsNone(rows[0]['sam_id'])

    def test_duplicates_in_either_base_block_automatic_fill(self):
        rows = self.compare(sources=[source(), source(id='sam-2')])
        self.assertEqual(rows[0]['situacao'], 'ambiguo')
        rows = self.compare([target(), target(id='other')])
        self.assertTrue(all(row['situacao'] == 'ambiguo' for row in rows))

    def test_training_and_unknown_instruments_never_allow_fill(self):
        for level in ('CULTO OFICIAL', 'CANDIDATO(A)', 'NÃO OFICIALIZADO'):
            with self.subTest(level=level):
                self.assertEqual(self.compare(sources=[source(source_level=level)])[0]['situacao'], 'nao_oficializado')
        for instrument in ('', 'A DEFINIR'):
            self.assertEqual(self.compare(sources=[source(source_instrument=instrument)])[0]['situacao'], 'sam_sem_instrumento')

    def test_composite_official_level_and_organists_are_supported(self):
        rows = self.compare(sources=[source(source_level='RJM / OFICIALIZADO(A)', source_instrument='ÓRGÃO')])
        self.assertEqual(rows[0]['situacao'], 'preencher')
        self.assertEqual(rows[0]['sam_instrumento'], 'ÓRGÃO')

    def test_removed_sam_records_are_not_authoritative(self):
        self.assertEqual(self.compare(sources=[source(missing_since='2026-10-20')])[0]['situacao'], 'sem_sam')

    def test_uses_sam_origin_instead_of_local_gem_fields(self):
        rows = self.compare(sources=[source(instrumento='VIOLONCELO', nivel='CANDIDATO(A)')])
        self.assertEqual(rows[0]['sam_instrumento'], 'VIOLINO')
        self.assertEqual(rows[0]['situacao'], 'preencher')

    def test_historical_official_catalog_is_included_with_explicit_origin(self):
        rows = self.compare(sources=[source(source_kind='sam_gem')])
        self.assertEqual(rows[0]['situacao'], 'preencher')
        self.assertEqual(rows[0]['sam_origem'], 'SAM')

    def test_current_sam_state_overrides_historical_gem_official_level(self):
        rows = self.compare(sources=[source(source_kind='sam_gem', id='gem-id'),
                                    source(source_level='CANDIDATO(A)', aluno_id='gem-id')])
        self.assertEqual(rows[0]['situacao'], 'nao_oficializado')
        self.assertEqual(rows[0]['sam_origem'], 'SAM')

    def test_historical_and_current_same_person_do_not_create_false_duplicate(self):
        rows = self.compare(sources=[source(), source(id='gem-id', source_kind='sam_gem')])
        self.assertEqual(rows[0]['situacao'], 'preencher')

    def test_sam_people_without_darpe_are_excluded(self):
        self.assertEqual(self.compare(targets=[]), [])
        rows = self.compare(sources=[source(), source(id='unrelated', source_name='OUTRA PESSOA')])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['darpe_id'], target()['id'])

    def test_territorial_scope_applies_to_both_sources(self):
        rows = self.compare(scope={'level': 'municipal', 'municipio': 'JANDIRA', 'comum': ''})
        self.assertEqual(rows, [])
        rows = self.compare(scope={'level': 'local', 'municipio': 'ITAPEVI', 'comum': CATALOG[1]['comum']})
        self.assertEqual(rows, [])

    @patch('ColorAdminApp.modules.darpe_sam.requests.patch')
    def test_fill_guards_empty_instrument_and_unchanged_snapshot(self, update):
        update.return_value.json.return_value = [{'id': target()['id']}]
        count = fill_confirmed(self.compare(), {'id': 'actor', 'name': 'Operador'})
        self.assertEqual(count, 1)
        options = update.call_args.kwargs
        self.assertIn('updated_at.eq.', options['params']['or'])
        self.assertIn('instrumento_oficializado.is.null', options['params']['and'])
        self.assertEqual(options['json']['instrumento_oficializado'], 'VIOLINO')
        self.assertNotIn('darpe_musico', options['json'])
        self.assertEqual(options['json']['updated_by_user_id'], 'actor')

    @patch('ColorAdminApp.modules.darpe_sam.requests.patch')
    def test_fill_never_updates_divergences_or_ambiguous_records(self, update):
        rows = self.compare([target(instrumento_oficializado='VIOLONCELO')])
        self.assertEqual(fill_confirmed(rows, {'id': 'actor', 'name': 'Operador'}), 0)
        update.assert_not_called()

    @patch('ColorAdminApp.modules.darpe_sam.read_comparison')
    def test_get_is_read_only_and_paginates(self, read):
        read.return_value = (self.compare() * 250, '2026-10-21T10:00:00Z')
        response = api(request_for('/darpe/api/conferencia-sam/?pagina=2'))
        data = json.loads(response.content)
        self.assertEqual(len(data['items']), 100)
        self.assertEqual(data['total'], 250)
        self.assertEqual(data['paginas'], 3)
        self.assertIn('no-store', response['Cache-Control'])

    @patch('ColorAdminApp.modules.darpe_sam.read_comparison')
    @patch('ColorAdminApp.modules.darpe_sam.fill_confirmed')
    def test_post_recomputes_candidates_and_respects_filters(self, fill, read):
        rows = self.compare()
        read.return_value = (rows, None)
        fill.return_value = 1
        response = api(request_for('/darpe/api/conferencia-sam/preencher/?cidade=JANDIRA', 'post'), 'preencher')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fill.call_args.args[0], [])

    @patch('ColorAdminApp.modules.darpe_sam.can_access_module', return_value=False)
    @patch('ColorAdminApp.modules.darpe_sam.read_comparison')
    def test_unauthorized_access_reads_nothing(self, read, _allowed):
        self.assertEqual(api(request_for('/darpe/api/conferencia-sam/')).status_code, 403)
        read.assert_not_called()

    def test_page_and_write_route_method(self):
        response = page(request_for('/darpe/conferencia-sam/'))
        self.assertContains(response, 'Conferência DARPE × SAM')
        self.assertEqual(api(request_for('/darpe/api/conferencia-sam/preencher/'), 'preencher').status_code, 405)
        self.assertEqual(resolve('/darpe/conferencia-sam/').func, page)
        self.assertEqual(resolve('/darpe/api/conferencia-sam/').func, api)
        self.assertEqual(resolve('/darpe/api/conferencia-sam/preencher/').kwargs, {'action': 'preencher'})

    def test_filters_match_comum_status_and_query(self):
        rows = self.compare()
        self.assertEqual(len(filtered(rows, {'q': 'grangeiro', 'situacao': 'preencher'})), 1)
        self.assertEqual(filtered(rows, {'comum': CATALOG[1]['comum']}), [])
