# Vigência de cargo, comum e formação musical

Aplicar as migrações 037 e 038, nessa ordem, antes de sincronizar o SAM.
A 038 também atualiza a função da 037 para instalações que já a executaram.

`sam_cadastro_historico` conserva os valores completos anteriores e posteriores
na mesma transação da atualização do cadastro, inclusive alterações de ingresso.
`sam_cadastro_transicoes` conserva cada campo com sua própria data e evidência.
Nenhuma das duas tabelas permite alteração ou exclusão pelo serviço da aplicação.
Os backups novos incluem as duas tabelas; backups anteriores continuam aceitos.

As datas têm significados diferentes:

- `effective_at`, com `date_basis=sam`: data da mudança documentada no SAM.
- `effective_at`, com `date_basis=manual`: vigência registrada por uma fonte manual anterior.
- `date_basis=detected_at_sync`: data de observação; não comprova quando a mudança ocorreu no SAM.
- `detected_at`: quando esta aplicação preservou a evidência.

A sincronização dos logs importa automaticamente transições quando o registro
contém `student_id`, `before` e `after` com os nomes dos campos locais, além da
data original do log. Um texto genérico como "Salvou aluno" não identifica os
campos alterados e não autoriza atribuir uma data de promoção. Logs brutos
continuam preservados para investigação.

Para evidências recuperadas de exportações do SAM, preparar um JSON como abaixo.
O exemplo usa identidade fictícia; substituir todos os valores pela evidência real.

```json
[
  {
    "source_key": "IDENTIFICADOR_ORIGINAL_SAM",
    "campo": "nivel",
    "anterior": "RJM",
    "posterior": "CULTO OFICIAL",
    "effective_at": "2025-04-20T10:30:00-03:00",
    "source_ref": "sam-log:IDENTIFICADOR_DO_LOG",
    "evidence": {"arquivo": "exportacao_sam.json", "registro": "IDENTIFICADOR_DO_LOG"}
  }
]
```

Validar sem gravação:

```powershell
python manage.py import_sam_transitions caminho/arquivo.json
```

Gravar as evidências validadas:

```powershell
python manage.py import_sam_transitions caminho/arquivo.json --commit
```

Campos aceitos: `cargo_ministerio`, `comum_congregacao`, `municipio`, `nivel`,
`data_inicio_gem`, `status` e `instrumento`. Registrar cada transição de nível
individualmente, inclusive ingresso, RJM, Culto Oficial e oficialização de músicos
e organistas. Reimportar a mesma referência é idempotente; divergências sob a
mesma referência são recusadas. Cada registro é atômico; uma importação interrompida
pode ser repetida sem duplicar os registros concluídos.

O acompanhamento usa a vigência na data local do evento (São Paulo). Como os
eventos têm apenas data, alterações no mesmo dia usam o estado ao final desse dia.
Participações e conferências nominais preservam seu cargo e sua comum originais.
Filtros e contagens usam esses valores por evento, inclusive para pessoas que
deixaram o cargo. Ausências automáticas exigem cargo e localidade historicamente
conhecidos; uma captura recente não produz faltas retroativas.

O histórico do GEM apresenta ingresso e as transições de cargo, localidade e nível,
identificando explicitamente datas de detecção sem vigência comprovada. A antiga
`sam_level_history` continua preservada e é integrada ao novo registro.

Sem data original e valores suficientes, a vigência fica pendente. Os exemplos de
Henrique e Jeferson não são cadastrados por nome nem recebem datas presumidas.
É necessário recuperar os respectivos registros originais do SAM para confirmar
a data exata da mudança; listas nominais de janeiro e do Brás já conservam o cargo
de cada participação independentemente dessa recuperação.
