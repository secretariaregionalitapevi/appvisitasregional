from unittest.mock import patch

import requests
from django.test import SimpleTestCase
from ColorAdminApp.modules.gem_darpe import attach_membership, enrich


class GemDarpeTests(SimpleTestCase):
    def setUp(self):
        self.catalog = [{'comum': 'BR-21-1020 - NHAMBUCA', 'cidade': 'CAUCAIA DO ALTO'},
                        {'comum': 'BR-22-3489 - INFANTS GARDEN', 'cidade': 'JANDIRA'}]
        self.student = {'id': '1', 'nome_aluno': 'EDMILSON FERNANDES GUILHERME',
                        'comum_congregacao': self.catalog[0]['comum'], 'municipio': 'CAUCAIA DO ALTO'}
        self.member = {'id': 'd', 'nome_completo': 'Edmilson Fernandes Guilherme',
                       'comum_congregacao': 'NHAMBUCA', 'cidade': 'CAUCAIA DO ALTO',
                       'status': 'ATIVO', 'darpe_musico': True}

    def test_badge_works_for_both_students_and_graduates(self):
        for level in ('CANDIDATO(A)', 'OFICIALIZADO(A)'):
            rows = [dict(self.student, nivel=level)]
            attach_membership(rows, [self.member], self.catalog)
            self.assertTrue(rows[0]['darpe_cadastrado'])
            self.assertNotIn('darpe_id', rows[0])

    def test_organist_and_legacy_combined_flag_are_supported(self):
        for field in ('darpe_organista', 'darpe_musico_organista'):
            rows = [dict(self.student)]
            attach_membership(rows, [{**self.member, 'darpe_musico': False, field: True}], self.catalog)
            self.assertTrue(rows[0]['darpe_cadastrado'])

    def test_other_person_common_inactive_and_non_musical_do_not_get_badge(self):
        for overrides in ({'nome_completo': 'EDMILSON FERREIRA SILVA'},
                          {'comum_congregacao': self.catalog[1]['comum'], 'cidade': 'JANDIRA'},
                          {'status': 'INATIVO'}, {'darpe_musico': False, 'darpe_colaborador': True}):
            rows = [dict(self.student)]
            attach_membership(rows, [{**self.member, **overrides}], self.catalog)
            self.assertFalse(rows[0]['darpe_cadastrado'])

    def test_ambiguous_duplicates_are_not_marked(self):
        rows = [dict(self.student)]
        attach_membership(rows, [self.member, {**self.member, 'id': 'duplicate'}], self.catalog)
        self.assertFalse(rows[0]['darpe_cadastrado'])

    def test_confirmed_alcides_spelling_is_limited_to_cardoso(self):
        common = 'BR-22-0673 - VILA DOUTOR CARDOSO'
        catalog = [{'comum': common, 'cidade': 'ITAPEVI'}, *self.catalog]
        students = [dict(self.student, nome_aluno='ALCIDES COELHO DE SOUZA',
                         comum_congregacao=common, municipio='ITAPEVI')]
        member = dict(self.member, nome_completo='ALCIDES COELHO DE SOUSA',
                      comum_congregacao=common, cidade='ITAPEVI')
        attach_membership(students, [member], catalog)
        self.assertTrue(students[0]['darpe_cadastrado'])
        students[0]['comum_congregacao'] = self.catalog[0]['comum']
        students[0]['municipio'] = 'CAUCAIA DO ALTO'
        attach_membership(students, [member], catalog)
        self.assertFalse(students[0]['darpe_cadastrado'])

    @patch('ColorAdminApp.modules.gem_darpe.read_members', side_effect=requests.Timeout)
    def test_unavailable_darpe_does_not_block_gem_or_claim_no_membership(self, _):
        rows = [dict(self.student)]
        self.assertFalse(enrich(rows))
        self.assertIsNone(rows[0]['darpe_cadastrado'])
