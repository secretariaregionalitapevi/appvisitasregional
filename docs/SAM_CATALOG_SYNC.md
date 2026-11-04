# Espelhamento do cadastro completo do SAM

A rotina automática lê duas listagens do SAM autenticado:

- **Membros** (`grp_musical`): cadastro atual de músicos, organistas e ministério.
- **Alunos** (`alunos`): complemento de alunos e vínculos com o histórico pedagógico.

As pessoas são conciliadas pelo identificador original do SAM. Quando um cadastro
local antigo ainda não tem identificador, a rotina tenta nome completo e comum,
depois contexto de município e instrumento. Homônimos não resolvidos permanecem
na fila de conferência; não são associados por aproximação.

O cadastro Membros prevalece para cargo, nível, instrumento e comum atuais quando
o mesmo identificador aparece nas duas páginas. O identificador original passa a
ser preservado também no cadastro local já existente, mantendo seu UUID e vínculos.
Uma transferência de comum atualiza a mesma pessoa e aciona a auditoria temporal.
Cadastros não são excluídos pela sincronização.

## Atualização manual

Prévia sem gravação:

```powershell
python manage.py sync_sam_members --report .backups/sam-catalogo-previa.json
```

Atualizar o cadastro completo:

```powershell
python manage.py sync_sam_members --commit --report .backups/sam-catalogo-aplicado.json
```

O comando localiza o scraper configurado em `SAM_SCRAPER_DIR` ou a pasta irmã
`PROJETO_SAM*`. O SAM original é acessado somente para leitura.

`sync_sam_audit --full` preserva **logs de auditoria**; não substitui a atualização
do cadastro completo. A rotina automática `run_sam_sync_worker` já usa a mesma
captura integral implementada em `sync_sam_members`.

## Conferência da cobertura

As requisições preservam o método e as colunas reais de cada listagem e removem
filtros de pesquisa da captura. A paginação é percorrida até o fim do recorte.
As ordens de Instrumento e Nível são diferentes entre Membros e Alunos e são
identificadas pelos cabeçalhos, não por uma posição comum às duas páginas.

Alunos pode repetir a mesma pessoa com a anotação visual `(compartilhado)`.
Essa anotação não faz parte do nome. Identificadores associados a nomes distintos
são recusados; os campos atuais são obtidos de Membros.

Os contadores do SAM podem divergir das identidades retornadas. Quando isso
ocorre, a rotina exige uma segunda leitura integral independente e compara os
conjuntos exatos de identificador e nome com a captura paginada. Se divergirem,
a captura é recusada antes da gravação. A divergência de contador é registrada
nos metadados de cobertura, em vez de ser escondida.

As mudanças detectadas não recebem uma data histórica presumida. As migrações
037 e 038 devem estar aplicadas para preservar antes/depois e a vigência temporal.
Pessoas que aparecem somente em Membros são monitoradas pelo catálogo, sem serem
enviadas indevidamente à fila de aulas do GEM.

Depois de atualizar o código, reiniciar o worker em execução para que ele carregue
a nova rotina. O supervisor `scripts/run_sam_worker.ps1` reinicia automaticamente
o processo quando ele é encerrado durante uma pausa de manutenção.
