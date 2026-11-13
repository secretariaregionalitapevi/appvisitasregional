"""Batch exam writes and shared totals, without changing canonical result codes."""
from collections import defaultdict
from datetime import datetime
import requests
from django.conf import settings
from django.core.cache import cache
from . import music_exams as exams
from .access_control import service_headers
from .exam_identity import save_identity
from .gem import _milestones, SUMMARY_FIELDS


def update_cache_many(students):
    if not students:
        return
    rows=cache.get('gem:students:v7')
    if rows is None:
        return
    fields=SUMMARY_FIELDS.split(',')
    changes={str(s['id']):{field:s[field] for field in fields if field in s} for s in students}
    existing={str(row.get('id')) for row in rows}
    rows=[dict(row,**changes[str(row['id'])]) if str(row.get('id')) in changes else row for row in rows]
    rows.extend(row for key,row in changes.items() if key not in existing)
    cache.set('gem:students:v7',rows,300)


def uniform_payloads(payloads):
    keys = sorted(set().union(*(p.keys() for p in payloads)))
    # The database supplies IDs for new rows and preserves existing IDs on conflict.
    keys = [k for k in keys if k not in {'id','created_at','updated_at'}]
    return [{key:p.get(key) for key in keys} for p in payloads]


def save_exams(payloads):
    if not payloads:
        return []
    values = uniform_payloads(payloads)
    def write(rows):
        return requests.post(exams.rest_url(),params={'on_conflict':'chave_idempotencia'},
            headers=service_headers('resolution=merge-duplicates,return=representation'),json=rows,timeout=(5,45))
    response = write(values)
    if response.status_code == 400:
        try:
            error = response.json()
        except ValueError:
            error = {}
        if error.get('code') in {'42703','PGRST204'} and 'agenda_evento_' in str(error):
            compatible=[]
            for row in values:
                item={k:v for k,v in row.items() if not k.startswith('agenda_evento_')}
                if row.get('agenda_evento_id') and row.get('agenda_evento_data'):
                    day=datetime.strptime(row['agenda_evento_data'],'%Y-%m-%d').strftime('%d/%m/%Y')
                    notes=exams.AGENDA_NOTE.sub('',row.get('observacoes') or '').strip()
                    item['observacoes']='\n'.join(filter(None,[notes,f"Agenda: {row.get('agenda_evento_titulo')} | {day} {row.get('agenda_evento_hora') or ''} | ID: {row['agenda_evento_id']}"]))
                compatible.append(item)
            response=write(compatible)
    response.raise_for_status()
    saved=response.json()
    if {r.get('chave_idempotencia') for r in saved} != {r['chave_idempotencia'] for r in values}:
        raise requests.RequestException('O banco não confirmou todos os exames do lote.')
    return saved


def sync_shared(exam_rows):
    values=[]
    for row in exam_rows:
        _,totals=exams.dashboard_summary([],[dict(row,origem='PAINEL')])
        values.append({'id':row['id'],'data_exame':row['data_exame'],'municipio':row.get('municipio'),
            'lancado_por':row.get('lancado_por') or 'Importação de exames','total_exames':totals['total'],
            **{field:totals[field] for field in exams.LEGACY_FIELDS}})
    if not values:
        return
    response=requests.post(settings.SUPABASE_URL+'/rest/v1/musica_exames_lancamentos',params={'on_conflict':'id'},
        headers=service_headers('resolution=merge-duplicates,return=minimal'),json=values,timeout=(5,45))
    response.raise_for_status()


def update_stages(pairs,changes=None):
    pairs=list(pairs)
    own_cache=changes is None
    changes={} if changes is None else changes
    student_ids=sorted({str(student['id']) for student,_ in pairs})
    current_levels={}
    url=settings.SUPABASE_URL+'/rest/v1/musica_acompanhamento_aluno'
    for start in range(0,len(student_ids),100):
        selected=student_ids[start:start+100]
        response=requests.get(url,headers=service_headers(),
            params={'select':'id,nivel','id':'in.('+','.join(selected)+')','limit':len(selected)},timeout=(5,20))
        response.raise_for_status()
        current_levels.update({str(row['id']):row.get('nivel') for row in response.json()})
    if set(current_levels)!=set(student_ids):
        raise requests.RequestException('Um cadastro de aluno não foi encontrado durante a atualização do nível.')
    students={}
    stages=defaultdict(list)
    for source_student,exam in pairs:
        student=dict(source_student,nivel=current_levels[str(source_student['id'])])
        key=str(student['id']);students[key]=student
        stage=exams.approved_stage(exam)
        if stage and _milestones(student.get('nivel'))[stage[0]]['status']=='future':
            stages[key].append(stage)
    groups=defaultdict(list)
    for key,eligible in stages.items():
        student=students[key]
        stage=max(eligible,key=lambda x:x[0]);level=stage[2]
        if stage[0]==4 and ('RJM' in exams.norm(student.get('nivel')) or any(s[0]==2 for s in eligible)):
            level='RJM / '+level
        groups[(student.get('nivel'),level,stage[0])].append(key)
    for (before,level,index),ids in groups.items():
        for start in range(0,len(ids),100):
            selected=ids[start:start+100]
            response=requests.patch(url,headers=service_headers('return=representation'),
                params={'id':'in.('+','.join(selected)+')','nivel':'is.null' if before is None else 'eq.'+before},
                json={'nivel':level},timeout=(5,30))
            response.raise_for_status()
            changed=response.json()
            for student in changed:
                changes[str(student['id'])]=student
            missing=set(selected)-{str(s['id']) for s in changed}
            if missing:
                # A concurrent promotion must never be overwritten or reported as a failure.
                response=requests.get(url,headers=service_headers(),params={'select':'*','id':'in.('+','.join(sorted(missing))+')'},timeout=(5,20))
                response.raise_for_status();current=response.json()
                if {str(s['id']) for s in current}!=missing or any(_milestones(s.get('nivel'))[index]['status']=='future' for s in current):
                    raise requests.RequestException('Um cadastro mudou durante a importação. Repita a confirmação.')
                for student in current:
                    changes[str(student['id'])]=student
    if own_cache:
        update_cache_many(list(changes.values()))


def commit_prepared(prepared, source_rows):
    changes={}
    try:
        return _commit_prepared(prepared,source_rows,changes)
    finally:
        update_cache_many(list(changes.values()))


def _commit_prepared(prepared, source_rows, changes):
    identities={};records={};writes={};pairs=[];new_keys=set();created=renamed=0
    for index,student,payload,old,choice,creating in prepared:
        key=str(student['id'])
        if key not in identities:
            previous=student.get('nome_aluno')
            changing_name=choice.get('atualizar_nome') and exams.norm(previous)!=exams.norm(source_rows[index]['nome'])
            if creating or changing_name:
                identities[key]=save_identity(student,source_rows[index],choice,creating,update_cache=False)
            else:
                identities[key]=student
            changes[key]=identities[key]
            created+=int(creating)
            renamed+=int(not creating and previous!=identities[key].get('nome_aluno'))
        student=identities[key]
        payload=dict(payload,nome_aluno=student.get('nome_aluno'))
        if not old:
            payload['chave_idempotencia']=exams.idempotency_key(payload)
        natural_key=payload['chave_idempotencia']
        if not old:
            new_keys.add(natural_key)
        if not old or (old.get('resultado')=='AGENDADO' and payload['resultado']!='AGENDADO'):
            if old:
                payload.update(prova_url=old.get('prova_url'),prova_nome=old.get('prova_nome'))
            writes[natural_key]=payload
        else:
            records[natural_key]=old
        pairs.append((student,natural_key))
    records.update({row['chave_idempotencia']:row for row in save_exams(list(writes.values()))})
    # Every mirrored row keeps the individual exam's stable ID, including retries.
    sync_shared(list({r['id']:r for r in records.values()}.values()))
    update_stages([(student,records[key]) for student,key in pairs],changes)
    imported=len(new_keys)
    return {'ok':True,'importados':imported,'duplicados':len(records)-imported,
            'cadastrados':created,'nomes_atualizados':renamed,'errors':[]}
