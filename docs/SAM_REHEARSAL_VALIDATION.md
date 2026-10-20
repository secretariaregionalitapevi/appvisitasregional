# Ensaio local de recuperação — Vila das Chácaras

Turma: GRUPO 02 - 2026. Destino: base SQLite isolada em `.backups/sam/rehearsals.sqlite3`.
Comum: BR-22-2999 — Vila das Chácaras. Município: Itapevi.
Não houve envio ao SAM original nem criação de registros nas tabelas do Supabase.
As chamadas HTTP foram bloqueadas durante a criação, leitura e repetição do ensaio real.

## Registros recriados no teste

| Conjunto | Registros |
|---|---:|
| Turma | 1 |
| Alunos | 12 |
| Matrículas | 12 |
| Aulas | 18 |
| Chamadas | 216 |
| Históricos individuais | 269 |

| Histórico individual | Registros |
|---|---:|
| MSA | 188 |
| Método | 6 |
| Hinário | 41 |
| Provas | 0 |
| Escalas | 34 |
| Progresso/atividades | 0 |

Os 12 alunos tiveram um vínculo único entre o identificador de membro e o cadastro local.
Não houve associação automática por nome. Não foram inventadas provas ou atividades.
O histórico individual inclui os registros identificados por aluno em toda a cópia, podendo
abranger outras turmas/localidades; não foi relacionado a uma aula apenas por coincidência de data.

## Conferência

- Todos os campos de todos os lançamentos recriados foram comparados com os registros originais da cópia.
- Datas, fases, páginas, lições, claves, métodos, hinos, vozes, observações e responsáveis foram preservados.
- Campos ausentes permaneceram ausentes. Marcadores “EM GRUPO” foram preservados nas observações.
- Chaves estrangeiras garantiram os vínculos na base de teste; conteúdos e contagens passaram na conferência.
- A execução foi repetida: mesmos identificadores e mesmos registros, sem duplicidades.
- A API consultou o ensaio persistido sem usar a rede e retornou HTTP 200.
- O JavaScript da ficha foi executado em DOM de teste: seis abas, colunas pedagógicas e acesso aos lançamentos nas 12 matrículas conferidos, sem navegador ou rede.
- 50 testes de backup/ensaio passaram. A página Django renderizou com HTTP 200 e o JavaScript foi verificado.

## Como consultar

GEM → Backup SAM → Ensaio de recuperação. O último ensaio é carregado ao abrir a página.
Abra “Alunos recriados no ensaio” ou uma matrícula/chamada e clique em “Ver aluno e lançamentos”.
As abas MSA, Provas, Método, Hinário, Escalas e Progresso mostram as colunas próprias de cada categoria.

Este resultado demonstra a recriação local do acervo. Não comprova compatibilidade de escrita no SAM
nem cobertura integral dos dados que existiam na origem. O envio ao SAM depende de um plano revisado,
operações suportadas e autorização posterior; não existe adaptador de escrita nesta implementação.

Ensaio: `e3237c3b-ebbf-5353-b579-47170ca7ff77`.

Cópia de origem: `99edf49d-fd07-40b7-ac48-750d4c6f9d68`.
