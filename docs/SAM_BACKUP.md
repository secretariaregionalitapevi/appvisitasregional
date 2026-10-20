# Backup SAM — acervo pessoal e recuperação em estudo

## Limite desta versão

Esta central pertence ao sistema pessoal de gestão. Não é oficial nem autorizada pelo SAM.
Nenhuma rota, botão ou comando desta implementação escreve no SAM original, abre sua sessão
ou altera tabelas do espelho. As escritas são a criação de novos arquivos locais de backup e de registros na base SQLite isolada do ensaio.
O plano de recuperação é um diagnóstico local e permanece bloqueado, mesmo sem pendências.
Não foi implementado um adaptador reverso, sequer oculto por uma configuração.

## Consulta

Menu GEM → Backup SAM, em `/gem/sam/backup/`, restrito a sessão autenticada com role_id 1 (Master).
Selecione a fonte (espelho atual ou uma versão preservada), município e comum.
Quando há versões disponíveis, a página abre a mais recente, evitando uma nova leitura completa da base.
A identificação usa código BR; descrição sem código só é associada ao catálogo quando inequívoca.
Os municípios são normalizados por caixa, acentuação e espaços, com a grafia do catálogo em maiúsculas.
Para comuns fora do catálogo, o município é recuperado primeiro de `source_payload.city` do cadastro original
e, na ausência dessa evidência, do cadastro local da mesma comum. Não se usa município de alunos
que apenas frequentam uma turma em outra localidade. Município conflitante ou ausente gera pendência
separada, nunca uma opção fictícia no seletor. Não se associa aluno por nome.
As turmas são selecionadas pela localidade onde funcionam; alunos de outras comuns matriculados nelas
participam do recorte. Históricos individuais podem incluir outras localidades e não são automaticamente
atribuídos à turma consultada. As aulas sem turma e os históricos sem cadastro ficam destacados.
O diagnóstico geral identifica também vínculos perdidos fora da localidade selecionada.

## Preservação

O botão “Preservar cópia completa” lê todas as tabelas previstas, independentemente do filtro.
O comando equivalente é `python manage.py backup_sam`.
São incluídos catálogo de comuns, turmas, matrículas, aulas, chamadas, cadastros de alunos,
estados de sincronização, mudanças de nível, auditoria e as seis tabelas de acompanhamento.
Não inclui as demais pastas do sistema, configuração, credenciais, banco Django ou arquivos binários de anexos.

A leitura é paginada e exige contagem exata; falhas, contagens variáveis ou IDs repetidos recusam a captura.
As tabelas são lidas separadamente: não se trata de um snapshot transacional do Supabase.
Mesmo contagens estáveis não provam consistência durante alterações simultâneas. Preferir um intervalo
em que os sincronizadores do espelho não estejam gravando. Esta central não pausa serviços automaticamente.

Cada captura é um arquivo JSON comprimido com UUID exclusivo, versão de esquema, intervalo de leitura,
responsável, dados originais e SHA-256 do conteúdo completo, exceto o próprio campo SHA-256.
A publicação ocorre somente depois da escrita completa. Versões existentes nunca são sobrescritas
pela aplicação, e não há endpoint para excluir ou editar versões. Isso não impede alterações por quem tem
acesso ao disco: SHA-256 detecta corrupção acidental, não autentica o arquivo contra alteração intencional.
A listagem usa um índice derivado e confere o SHA-256 do arquivo comprimido; índices perdidos ou inválidos são reconstruídos.
A consulta e o download descomprimem a cópia e revalidam a integridade do conteúdo. Cópias inválidas não podem ser usadas.
O JSON é um arquivo técnico de recuperação: preserva tipos, nomes e datas originais, sem formatação de relatório.
Datas na interface e no nome de download seguem o padrão do projeto. PDF e Excel não foram adicionados.

## Armazenamento e operação

Por padrão: `.backups/sam/`, fora de static/media e ignorado pelo Git. O download exige Master.
`SAM_BACKUP_DIR` permite configurar outro diretório persistente via variável de ambiente.
Em produção a aplicação recusa criar cópias se esse diretório não estiver explicitamente configurado;
um filesystem temporário, como o de uma função serverless, não oferece preservação durável.
Esta versão funciona localmente e não deve ser habilitada em funções serverless com tempo de execução
insuficiente para capturar todas as tabelas. Deve-se usar o comando em um processo persistente.

O armazenamento padrão está nesta mesma máquina e pode estar na mesma conta OneDrive do projeto.
Baixar uma cópia e guardá-la em armazenamento independente. Restringir o acesso, pois contém dados pessoais.
A captura é manual nesta versão. O comando permite agendamento posterior no Windows, mas nenhum
agendamento foi instalado. Reter versões antigas: uma nova cópia não recupera valores já sobrescritos.
Para recuperação completa do banco do sistema pessoal, também é necessário backup nativo do Supabase.

## Lacunas que impedem prometer restauração completa

- O acervo prova apenas os dados que foram capturados; ausência de pendências não prova cobertura do SAM.
- Matrículas derivadas de chamadas podem omitir alunos sem chamadas capturadas.
- Vínculos criados anteriormente por nome precisam ser conferidos por identificadores de origem.
- Origem de lançamentos locais/importados e vínculo de histórico com uma turma exigem revisão.
- Só as URLs de anexos estão preservadas; os arquivos binários ainda precisam de uma estratégia própria.
- Não há comparação automática com o SAM nem teste de criação no SAM nesta etapa. O ensaio disponível escreve somente na base local isolada.

## Critérios para uma fase futura de restauração

1. Preservar e conferir uma versão anterior à perda, quando disponível; inventariar Vila das Chácaras.
2. Revisar campos, identidade de alunos, vínculos, completude e procedência dos lançamentos.
3. Consultar a origem em modo somente leitura para identificar registros existentes e conflitos.
4. Verificar com responsáveis pelo SAM quais operações são suportadas e autorizadas para dados históricos.
5. Construir adaptador separado, testar primeiro com fixtures e ambiente isolado, sem credenciais de produção.
6. Ensaiar turmas, matrículas, aulas, chamadas e lançamentos com mapa de IDs antigos/novos.
7. Demonstrar ausência de duplicidades, retomada após falha, preservação do que já existe e conferência pós-operação.
8. Submeter um plano concreto para autorização do proprietário e dos responsáveis necessários antes de qualquer escrita real.

O ensaio local confere registros, contagens, relações e repetição sem duplicidade; não valida operações ou comportamento do SAM. Os critérios que dependem do SAM e de autorização continuam pendentes. Não é possível garantir risco zero;
a evidência do ensaio e as operações suportadas precisam ser avaliadas antes de uma decisão.


## Ensaio local de recriação

A aba “Ensaio de recuperação” já permite consultar o teste executado ou recriar uma turma
a partir de uma cópia preservada. O destino é fixo: Vila das Chácaras, BR-22-2999, Itapevi.
Outras comuns e turmas são rejeitadas no servidor, mesmo se o cliente enviar um filtro diferente.
O teste não usa credenciais, sessão ou endpoints do SAM. Não grava nas tabelas do Supabase.

A base separada fica em `.backups/sam/rehearsals.sqlite3`, junto ao acervo privado ignorado pelo Git.
Os registros são efetivamente inseridos em SQLite, com chaves estrangeiras, transação e mapa
entre identificadores preservados e identificadores do ensaio. Não é só uma prévia de JSON.
Uma falha de conferência reverte a criação inteira. A repetição da mesma cópia/turma/versão
reutiliza o ensaio e seus identificadores, sem duplicar registros.

A conferência compara todos os campos e vínculos persistidos com os propostos pela cópia.
Datas, números, páginas, lições, vozes, notas zero, observações, marcadores de estudos em grupo,
responsáveis e valores nulos são preservados. Não se substitui responsável ausente pelo instrutor.
Documentos continuam por referência, sem download ou envio de arquivos binários.

Alunos são vinculados por IDs de membro/cadastro. Conflitos de identidade deixam o histórico
pendente, sem associar pelo nome. Matrícula/chamada sem cadastro pode aparecer no teste,
mas nenhum histórico é inventado para esse aluno. A ausência de uma categoria não cria
um registro fictício para preenchê-la.

Os estudos copiados pertencem ao histórico individual completo do aluno, que pode abranger
outras turmas/localidades. Eles não recebem vínculo artificial com turma ou aula pela data.
A ficha acessível na matrícula/chamada exibe MSA, provas, método, hinário, escalas e progresso
com todas as colunas pedagógicas. “EM GRUPO” só aparece quando o marcador foi preservado
nas observações; isso não comprova qual turma/aula originou o estudo.

O teste local NÃO é demonstração de compatibilidade de escrita no SAM. Essa fase exige
comparação com a origem, verificação das operações suportadas, revisão do plano e autorização.


## Cadastro completo das turmas

A sincronização agora consulta `/turmas/editar/{id}` para todos os IDs preservados
e os acessíveis na listagem, incluindo finalizadas (`status=0`). O espelho mantém
`source_payload.registration` com os valores originais do formulário, IDs e nomes
de curso/igreja/responsáveis, dia da semana, horários, modalidade, datas, ativo,
proveniência, data de captura e indicação de campos pendentes. As datas continuam
nas colunas `data_inicio` e `data_termino`. Não requer alteração de esquema.

Para atualizar somente as turmas:

```powershell
python manage.py sync_sam_classes --groups-only
```

A sincronização normal de aulas usa a mesma captura. Aulas e auditoria reutilizam
o cadastro existente e não o substituem por informações parciais. Turmas apagadas
ou sem acesso mantêm os dados anteriores; a ausência fica pendente e não é usada
para inventar datas ou configuração. O comando escreve somente no espelho pessoal,
nunca no SAM original. Backups antigos são imutáveis: preserve uma nova cópia
após atualizar para incluir os campos novos. O painel exibe o cadastro da turma.

O checkbox Ativo do SAM é preservado sem alterações. Um período vencido aparece
como “Período encerrado”, mesmo se o checkbox continuar ativo; o painel não confunde
a configuração Ativo com a data de encerramento.

Na rotina automática, cadastros são revistos quando a listagem muda ou a captura
tem mais de 24 horas. `--groups-only` força a conferência de todas as turmas.
Isso evita reler milhares de formulários a cada ciclo de aulas.

Correção de cobertura: a captura une as listagens `status=0` e `status=1`,
confere cada página e valida a união dos IDs contra `recordsTotal`. A listagem
`status=0` sozinha não contém todas as turmas.
