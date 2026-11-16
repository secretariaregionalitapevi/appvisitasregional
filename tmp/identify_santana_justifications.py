import json
from pathlib import Path
from ColorAdminApp.modules.music_events import _registry, _leaders, _read
from ColorAdminApp.modules.access_control import common_catalog
from ColorAdminApp.modules.music_events_identity import CommonResolver, normalized_name
from ColorAdminApp.modules.music_events_import import is_local_conductor_role, norm, person_names

source = [
 ('Adonias','Cid S Pedro Gleba A','Trabalho'),
 ('Marcos','Pq Alvorada','Trabalho'),
 ('Roberto','Cristal Park IV','Trabalho'),
 ('Divã','Germano','Trabalho'),
 ('Jeferson','Pq Sinai','Trabalho'),
 ('Edson','Jaguari','Trabalho'),
 ('Gabriel Bento','Cristal Park III','Trabalho'),
 ('Carlos','Jd Bom Jesus','Questão familiar'),
 ('Elias','Itaquara Park km 50','Questão familiar'),
 ('Onofre','Central Parnaíba','Questão familiar'),
 ('Jorge','Jd Isaura','Idade avançada; primeiro encarregado local'),
 ('Otoniel','Jd Isaura','Cuidados com o pai enfermo; falecimento do pai informado na mensagem; segundo encarregado local'),
 ('Deivid','Pq Santana I','Cuidados com a esposa enferma, em tratamento de câncer'),
]
catalog=common_catalog()
resolver=CommonResolver(catalog)
people=_registry()
leaders=[]
for person in people:
    if not is_local_conductor_role(person.get('cargo_ministerio')) or norm(person.get('status')) in {'INATIVO','EXCLUIR'}:continue
    common=resolver.resolve(person.get('comum_congregacao'),person.get('municipio'))
    if common:
        leaders.extend({'name':name,'common':common} for name in person_names(person.get('nome_aluno')))
result=[]
for short, common_text, reason in source:
    tokens=set(normalized_name(short).split())
    matching=[p for p in leaders if tokens<=set(normalized_name(p['name']).split())]
    local=[p for p in matching if norm(p['common']['cidade']) in {'SANTANA DE PARNAIBA','PIRAPORA DO BOM JESUS'}]
    resolved={p['common']['comum']:p['common'] for p in local if resolver.resolve(common_text,p['common']['cidade'])==p['common']}
    result.append({'received_name':short,'received_common':common_text,'reason':reason,
                   'candidates':local,'resolved_commons':list(resolved)})
events=_read('musica_eventos',data_evento='eq.2026-11-15',order='created_at.desc')
Path('tmp/santana-justifications-identification.json').write_text(json.dumps({'event':events[0],'rows':result},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True))
