import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from ColorAdminApp.management.commands.sync_sam_catalog import Command
from ColorAdminApp.sam_catalog import parse_catalog
from ColorAdminApp.modules.music_ministry_domain import roster, history
from ColorAdminApp.modules.music_events_leaders import attach_leaders


class RegistryChangesTests(SimpleTestCase):
    def test_large_updates_use_batches_without_sending_personal_fields(self):
        command = Command(stdout=StringIO())
        targets = {str(i): {'id': str(i), 'nome_aluno': f'Pessoa {i}', 'telefone': 'protegido',
                            'status': 'Ativo', 'registro_msa': ''} for i in range(51)}
        with patch('ColorAdminApp.management.commands.sync_sam_catalog.requests.Session') as session:
            command._apply_students([(str(i), {'registro_msa': str(i)}) for i in range(51)], targets)
        rows = session.return_value.__enter__.return_value.post.call_args.kwargs['json']
        self.assertEqual(len(rows), 51)
        self.assertEqual(rows[0]['registro_msa'], '0')
        self.assertNotIn('telefone', rows[0])

    def test_member_transfer_repairs_existing_levi_and_binds_original_sam_id(self):
        document = {'rows': [{'cells': ['684274', 'LEVI DOS SANTOS', 'VILA DAS CHÁCARAS',
                    'MÚSICO', 'TROMPETE', 'OFICIALIZADO(A)'], 'source_kind': 'members', 'history_available': False}]}
        common = {'comum': 'BR-22-2999 - VILA DAS CHÁCARAS', 'cidade': 'ITAPEVI'}
        target = dict(id='levi', registro_msa='', nome_aluno='LEVI DOS SANTOS',
                      cargo_ministerio='MÚSICO', instrumento='TROMPETE', nivel='OFICIALIZADO(A)',
                      comum_congregacao='BR-22-0684 - JARDIM SANTA RITA - ITAPEVI', municipio='ITAPEVI')
        command = Command(stdout=StringIO())
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.json'
            path.write_text(json.dumps(document), encoding='utf-8')
            with patch.object(command, '_all', side_effect=[[target], []]), \
                 patch.object(command, '_post', return_value=[{'id': 'run'}]) as create, \
                 patch.object(command, '_patch') as update, \
                 patch.object(command, '_upsert_states') as states, \
                 patch('ColorAdminApp.management.commands.sync_sam_catalog.common_catalog', return_value=[common]):
                command.handle(input=path, commit=True, report=None)
        update.assert_any_call('musica_acompanhamento_aluno', 'levi', {
            'registro_msa': '684274', 'comum_congregacao': common['comum'], 'municipio': 'ITAPEVI'})
        self.assertEqual(states.call_args.args[0][0]['source_key'], '684274')
        self.assertEqual(states.call_args.args[0][0]['sync_status'], 'synced')
        self.assertFalse(any(call.args[0] == 'musica_acompanhamento_aluno' for call in create.call_args_list))

    def test_presence_follows_stable_identity_after_transfer(self):
        common = {'comum': 'BR-22-3129 - PARQUE SUBURBANO III', 'cidade': 'ITAPEVI'}
        registry = [{'id': 'jeferson', 'nome_aluno': 'JEFERSON',
                     'cargo_ministerio': 'Encarregado Local', 'status': 'Ativo',
                     'comum_congregacao': common['comum'], 'municipio': 'ITAPEVI'}]
        people = roster(registry, [], [common])
        result = history(people, [], [],
            [{'id': 'event', 'data_evento': '2026-05-17', 'titulo': 'Ensaio', 'tipo': 'ENSAIO_REGIONAL'}],
            [{'evento_id': 'event', 'sam_pessoa_id': 'jeferson', 'nome': 'JEFERSON',
              'comum_informada': 'CENTRAL', 'municipio_informado': 'ITAPEVI',
              'cargo': 'MÚSICO', 'situacao': 'PRESENTE'}],
            [common], {'level': 'regional'}, {'ano': 2026})
        self.assertEqual(result['rows'][0]['comum'], common['comum'])
        self.assertEqual(result['rows'][0]['present'], 1)
        self.assertEqual(result['unmatched'], 0)

    def test_unchanged_fingerprint_repairs_old_role_and_common(self):
        document = {'rows': [{'cells': ['123', 'JEFERSON',
                    'PARQUE SUBURBANO III | BR-SP-ITAPEVI-ITAPEVI',
                    'ENCARREGADO LOCAL', 'VIOLINO', 'OFICIALIZADO(A)']}]}
        student = parse_catalog(document)[0]
        target = {'id': 'person', 'registro_msa': '123', 'nome_aluno': 'JEFERSON',
                  'cargo_ministerio': 'MÚSICO', 'comum_congregacao': 'CENTRAL',
                  'municipio': 'ITAPEVI', 'instrumento': 'VIOLINO', 'nivel': 'OFICIALIZADO(A)'}
        state = {'id': 'state', 'source_key': '123', 'aluno_id': 'person',
                 'source_fingerprint': student['fingerprint'], 'source_level': student['level']}
        common = {'comum': 'BR-22-3129 - PARQUE SUBURBANO III', 'cidade': 'ITAPEVI'}
        command = Command(stdout=StringIO())
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.json'
            path.write_text(json.dumps(document), encoding='utf-8')
            with patch.object(command, '_all', side_effect=[[target], [state]]), \
                 patch.object(command, '_post', return_value=[{'id': 'run'}]), \
                 patch.object(command, '_patch') as update, \
                 patch.object(command, '_upsert_states'), \
                 patch('ColorAdminApp.management.commands.sync_sam_catalog.common_catalog', return_value=[common]):
                command.handle(input=path, commit=True, report=None)
        update.assert_any_call('musica_acompanhamento_aluno', 'person', {
            'cargo_ministerio': 'ENCARREGADO LOCAL', 'comum_congregacao': common['comum'],
            'municipio': 'ITAPEVI'})

    def test_replacement_does_not_revive_previous_leader_from_members(self):
        common = {'comum': 'BR-22-3129 - PARQUE SUBURBANO III', 'cidade': 'ITAPEVI'}
        central = {'comum': 'BR-22-1 - CENTRAL', 'cidade': 'ITAPEVI'}
        registry = [
            {'id': 'henrique', 'nome_aluno': 'HENRIQUE', 'cargo_ministerio': 'MÚSICO',
             'comum_congregacao': central['comum'], 'municipio': 'ITAPEVI', 'status': 'Ativo'},
            {'id': 'jeferson', 'nome_aluno': 'JEFERSON', 'cargo_ministerio': 'Encarregado Local',
             'comum_congregacao': common['comum'], 'municipio': 'ITAPEVI', 'status': 'Ativo'}]
        members = [{'id': 'old', 'nome': 'HENRIQUE', 'cargo_outros': 'Encarregado Local',
                    'comum': common['comum'], 'cidade': 'ITAPEVI', 'status': 'Ativo'}]
        people = roster(registry, members, [common, central])
        self.assertEqual([p['nome'] for p in people], ['JEFERSON'])
        data = {'rows': [{'comum': common['comum']} ]}
        attach_leaders(data, registry, [common, central], members)
        self.assertEqual(data['rows'][0]['encarregado_nomes'], ['JEFERSON'])
        # Even without a replacement, the obsolete membership row cannot restore him.
        attach_leaders(data, registry[:1], [common, central], members)
        self.assertEqual(data['rows'][0]['encarregado_nomes'], [])
