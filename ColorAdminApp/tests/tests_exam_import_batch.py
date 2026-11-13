import uuid
from unittest.mock import Mock, patch
import requests
from django.core.cache import cache
from django.test import SimpleTestCase
from ColorAdminApp import music_exams
from ColorAdminApp import exam_import_batch as batch


class ExamBatchImportTests(SimpleTestCase):
    def fixtures(self):
        prepared=[];source=[]
        for i in range(23):
            kind='RJM' if i<10 else 'CULTO OFICIAL' if i<18 else 'OFICIALIZAÇÃO'
            student=dict(id=str(uuid.UUID(int=i+1)),nome_aluno=f'Aluna {i}',nivel='CANDIDATO(A)',instrumento='ÓRGÃO',cargo_ministerio='ORGANISTA')
            payload=dict(aluno_id=student['id'],nome_aluno=student['nome_aluno'],data_exame='2026-11-07',tipo_exame=kind,
                         resultado='APROVADO',categoria='ORGANISTA',instrumento='ÓRGÃO',municipio='ITAPEVI',origem='IMPORTACAO',observacoes=None)
            payload['chave_idempotencia']=music_exams.idempotency_key(payload)
            prepared.append((i,student,payload,None,{},False));source.append({'nome':student['nome_aluno']})
        return prepared,source

    @patch('ColorAdminApp.exam_import_batch.update_cache_many')
    @patch('ColorAdminApp.exam_import_batch.save_identity',side_effect=lambda student,*args,**kwargs:student)
    @patch('ColorAdminApp.exam_import_batch.requests.get')
    @patch('ColorAdminApp.exam_import_batch.requests.patch')
    @patch('ColorAdminApp.exam_import_batch.requests.post')
    def test_23_results_use_one_exam_write_one_mirror_write_and_three_level_updates(self,post,update,get,identity,cache):
        prepared,source=self.fixtures();students={entry[1]['id']:entry[1] for entry in prepared};saved=[]
        current={key:dict(student) for key,student in students.items()}
        def write(url,**kwargs):
            response=Mock(status_code=201)
            if url.endswith('/musica_exames_individuais'):
                saved.extend(dict(row,id=str(uuid.UUID(int=1000+i))) for i,row in enumerate(kwargs['json']))
                response.json.return_value=saved
            return response
        def fetch_students(url,**kwargs):
            ids=kwargs['params']['id'][4:-1].split(',')
            response=Mock();response.json.return_value=[{'id':key,'nivel':current[key]['nivel']} for key in ids]
            return response
        def promote(url,**kwargs):
            ids=kwargs['params']['id'][4:-1].split(',');level=kwargs['json']['nivel']
            self.assertEqual(kwargs['params']['nivel'],'eq.CANDIDATO(A)')
            for key in ids:current[key]['nivel']=level
            response=Mock();response.json.return_value=[dict(students[key],nivel=level) for key in ids]
            return response
        post.side_effect=write;get.side_effect=fetch_students;update.side_effect=promote
        result=batch.commit_prepared(prepared,source)
        self.assertEqual(result['importados'],23)
        self.assertEqual(post.call_count,2)
        self.assertEqual(update.call_count,3)
        identity.assert_not_called()
        cache.assert_called_once()
        self.assertEqual(len(post.call_args_list[0].kwargs['json']),23)
        mirrors=post.call_args_list[1].kwargs['json']
        self.assertEqual(sum(row['organistas_rjm'] for row in mirrors),10)
        self.assertEqual(sum(row['organistas_culto_oficial'] for row in mirrors),8)
        self.assertEqual(sum(row['organistas_oficializacao'] for row in mirrors),5)
        self.assertEqual(sum(row['total_exames'] for row in mirrors),23)
        self.assertTrue(all('id' not in row for row in post.call_args_list[0].kwargs['json']))
        # Retrying completed exams reuses every ID and only refreshes their mirror.
        replay=[]
        for entry,old in zip(prepared,saved):
            i,student,payload,_,choice,creating=entry
            replay.append((i,dict(student,nivel=music_exams.approved_stage(old)[2]),payload,old,choice,creating))
        post.reset_mock();update.reset_mock()
        result=batch.commit_prepared(replay,source)
        self.assertEqual(result['duplicados'],23);self.assertEqual(result['importados'],0)
        post.assert_called_once();update.assert_not_called()
        self.assertEqual({r['id'] for r in post.call_args.kwargs['json']},{r['id'] for r in saved})

    @patch('ColorAdminApp.exam_import_batch.update_cache_many')
    @patch('ColorAdminApp.exam_import_batch.requests.patch')
    @patch('ColorAdminApp.exam_import_batch.requests.get')
    def test_stage_update_uses_authoritative_level_not_stale_import_preview(self,get,update,cache):
        prepared,_=self.fixtures();_,student,_,_,_,_=prepared[10]
        stale=dict(student,nivel='CULTO OFICIAL')
        exam={'tipo_exame':'CULTO OFICIAL','resultado':'APROVADO'}
        current=Mock();current.json.return_value=[{'id':student['id'],'nivel':'RJM / ENSAIO'}]
        get.return_value=current
        updated=dict(student,nivel='CULTO OFICIAL')
        response=Mock();response.json.return_value=[updated]
        update.return_value=response

        batch.update_stages([(stale,exam)])

        self.assertEqual(update.call_args.kwargs['params']['nivel'],'eq.RJM / ENSAIO')
        self.assertEqual(update.call_args.kwargs['json'],{'nivel':'CULTO OFICIAL'})
        cache.assert_called_once_with([updated])

    @patch('ColorAdminApp.exam_import_batch.update_cache_many')
    @patch('ColorAdminApp.exam_import_batch.requests.patch')
    @patch('ColorAdminApp.exam_import_batch.requests.get')
    def test_batch_keeps_rjm_prefix_only_for_officialization(self,get,update,cache):
        prepared,_=self.fixtures();_,student,_,_,_,_=prepared[10]
        current=Mock();current.json.return_value=[{'id':student['id'],'nivel':'RJM / ENSAIO'}]
        get.return_value=current
        updated=dict(student,nivel='RJM / OFICIALIZADO(A)')
        response=Mock();response.json.return_value=[updated]
        update.return_value=response

        batch.update_stages([(student,{'tipo_exame':'OFICIALIZAÇÃO','resultado':'APROVADO'})])

        self.assertEqual(update.call_args.kwargs['json'],{'nivel':'RJM / OFICIALIZADO(A)'})
        cache.assert_called_once_with([updated])

    @patch('ColorAdminApp.exam_import_batch.update_stages')
    @patch('ColorAdminApp.exam_import_batch.sync_shared')
    @patch('ColorAdminApp.exam_import_batch.save_exams')
    def test_existing_identity_is_added_to_student_cache_after_batch_import(self,save,shared,stages):
        prepared,source=self.fixtures()
        _,student,payload,old,choice,creating=prepared[0]
        student=dict(student,registro_msa='489527',comum_congregacao='BR-22-3510 - SÃO JOÃO',
                     municipio='ITAPEVI',nivel='CULTO OFICIAL')
        prepared=[(0,student,payload,old,choice,creating)]
        save.return_value=[dict(payload,id='exam-1')]
        cache_key='gem:students:v7'
        cache.set(cache_key,[],300)
        self.addCleanup(cache.delete,cache_key)

        result=batch.commit_prepared(prepared,source)

        self.assertTrue(result['ok'])
        self.assertEqual([row['id'] for row in cache.get(cache_key)],[student['id']])
        self.assertEqual(cache.get(cache_key)[0]['registro_msa'],'489527')

    @patch('ColorAdminApp.exam_import_batch.requests.post')
    def test_batch_falls_back_for_legacy_agenda_columns_and_preserves_human_notes(self,post):
        first=Mock(status_code=400);first.json.return_value={'code':'PGRST204','message':'agenda_evento_id missing'}
        second=Mock(status_code=201);second.json.return_value=[{'id':'existing','chave_idempotencia':'key'}]
        post.side_effect=[first,second]
        batch.save_exams([dict(id='never-overwrite-id',chave_idempotencia='key',observacoes='Anotação manual',
            agenda_evento_id='abc123',agenda_evento_data='2026-11-07',agenda_evento_titulo='Avaliação',agenda_evento_hora='09:00')])
        values=post.call_args.kwargs['json']
        self.assertNotIn('id',values[0]);self.assertNotIn('agenda_evento_id',values[0])
        self.assertIn('07/11/2026 09:00',values[0]['observacoes'])
        self.assertIn('Anotação manual',values[0]['observacoes'])

    @patch('ColorAdminApp.exam_import_batch.requests.post')
    def test_database_errors_are_not_hidden_as_success_or_retried_per_student(self,post):
        response=Mock(status_code=400);response.json.return_value={'code':'23514','message':'invalid result'}
        response.raise_for_status.side_effect=requests.HTTPError('invalid result');post.return_value=response
        with self.assertRaises(requests.HTTPError):batch.save_exams([{'chave_idempotencia':'key'}])
        post.assert_called_once()

    @patch('ColorAdminApp.exam_import_batch.update_cache_many')
    @patch('ColorAdminApp.exam_import_batch.requests.get')
    @patch('ColorAdminApp.exam_import_batch.requests.patch')
    def test_concurrent_promotion_is_never_downgraded(self,update,get,cache):
        prepared,_=self.fixtures();_,student,exam,*_=prepared[0]
        current=Mock();current.json.return_value=[dict(student,nivel=student['nivel'])]
        advanced=Mock();advanced.json.return_value=[dict(student,nivel='OFICIALIZADO(A)')]
        get.side_effect=[current,advanced]
        update.return_value.json.return_value=[]
        batch.update_stages([(student,exam)])
        self.assertEqual(update.call_args.kwargs['params']['nivel'],'eq.CANDIDATO(A)')
        cache.assert_called_once_with([dict(student,nivel='OFICIALIZADO(A)')])
