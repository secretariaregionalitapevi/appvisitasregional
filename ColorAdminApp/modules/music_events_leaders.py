"""Responsável cadastrado por comum, separado da conferência de presença."""
from collections import defaultdict
from .music_events_identity import CommonResolver
from .music_events_dashboard import code
from .music_events_import import norm


def attach_leaders(data,registry,catalog,members=()):
    resolver=CommonResolver(catalog);leaders=defaultdict(dict);sources={}
    for rows,source,name_field,role_field,common_field in [
        (registry,'Cadastro SAM','nome_aluno','cargo_ministerio','comum_congregacao'),
        (members,'Cadastro da irmandade','nome','cargo_outros','comum')]:
        source_names=defaultdict(dict)
        for row in rows:
            roles={norm(x) for x in str(row.get(role_field) or '').split(',')}
            if 'ENCARREGADO LOCAL' not in roles or norm(row.get('status')) in {'INATIVO','EXCLUIR'}:continue
            name=str(row.get(name_field) or '').strip()
            canonical=resolver.resolve(row.get('codigo_comum') or row.get(common_field),row.get('municipio') or row.get('cidade'))
            if not canonical or not name:continue
            source_names[code(canonical['comum'])][norm(name)]=name
        for key,names in source_names.items():
            if key not in leaders:leaders[key]=names;sources[key]=source
    for row in [*data['rows'],*data.get('conductors',{}).get('rows',[])]:
        key=row.get('comum_chave') or code(row['comum'])
        names=sorted(leaders.get(key,{}).values(),key=norm)
        row['encarregado_nomes']=names
        row['encarregado_nome']=' / '.join(names) if names else 'Não localizado no cadastro'
        row['encarregado_cadastro_fonte']=sources.get(key,'')
    return data
