# Validação inicial — Backup SAM

A cópia real foi gerada somente por leitura do espelho Supabase. Não houve acesso nem envio ao SAM original.
A página Django renderizou com HTTP 200 e cookie CSRF; o JavaScript passou em `node --check`.
A consulta ao arquivo real retornou HTTP 200 com todas as chamadas HTTP bloqueadas por mocks
(GET, POST, PATCH, PUT e DELETE), confirmando a consulta offline de uma versão preservada.

## Acervo completo preservado

15 tabelas, 211.083 registros. A cópia inclui 1.704 turmas, 12.726 aulas e 88.535 chamadas,
além do catálogo, matrículas, cadastros, estados de sincronização, evolução, estudos e auditoria.

## Vila das Chácaras

Município: Itapevi. Identidade de congregação: BR-22-2999.

| Conjunto | Registros preservados no recorte |
|---|---:|
| Turmas | 7 |
| Cadastros locais de alunos | 26 |
| Matrículas | 69 |
| Aulas | 77 |
| Chamadas | 863 |
| Lançamentos individuais | 371 |

Período das aulas capturadas: 01/02/2025 a 27/09/2026.
Os históricos individuais podem abranger outras localidades; não foram atribuídos a turmas por inferência.

74 pendências: 63 chamadas e 6 matrículas sem vínculo com cadastro local, mais 5 cadastros
sem identificador único no acervo SAM. As chamadas/matrículas sem cadastro local envolvem
3 identificadores distintos de alunos de origem; 69 pendências não significam 69 alunos diferentes.
Nenhum vínculo foi corrigido automaticamente e nenhum lançamento foi criado a partir desses indícios.

O diagnóstico global da cópia não encontrou chamadas sem aula, matrículas sem turma,
lançamentos individuais sem cadastro de aluno ou mudanças de nível sem cadastro de aluno.
Isso não comprova completude do SAM original: vínculos nulos nas chamadas ainda precisam ser revisados.

## Integridade e testes

38 testes passaram: leitura paginada com limite do servidor, mudança de contagem, IDs repetidos,
integridade da cópia e do índice, identificação de comuns por código BR, descrições ambíguas,
alunos de outras comuns, órfãos, controle Master, falha de captura, consulta offline,
download verificado e inexistência de rota de restauração. `python manage.py check` sem erros.

A cópia ainda não foi comparada com o SAM original. Restauração, anexos binários e agendamento
não foram implementados. As versões são criadas manualmente pelo botão ou comando `backup_sam`.

Identificador da cópia: `99edf49d-fd07-40b7-ac48-750d4c6f9d68`.

SHA-256 do conteúdo: `9e60bc31e59dcff148802ee326f1a0de5d45dc6fc063134a5c15d3c05cbbbde0`.


## Enriquecimento dos cadastros de turmas — 08/10/2026

As 1.704 turmas preservadas foram consultadas diretamente pelo formulário de
edição no SAM. Foram atualizadas 1.698 no espelho pessoal: 1.615 com todos os
campos esperados e 83 com campos vazios no original, marcados como incompletos.
Seis ficaram pendentes: IDs 23639, 26597, 59926, 59927 e 59928 retornaram identidade
incompleta; o ID 40643 apresentou descrição divergente entre cadastro e listagem.
Os cadastros anteriores dessas seis turmas foram mantidos. Nenhuma escrita no SAM.

As quatro turmas antigas da Vila das Chácaras (51474, 51475, 51476 e 51483) tiveram
os formulários completos capturados, incluindo responsável, modalidade e horários.
A turma 59927 recebeu `source_payload.restoration_proposal` com a configuração
informada pelo usuário para o piloto. Os dias substitutos foram definidos como
07/02/2026 e 25/11/2028 (primeiro/último sábado dos meses solicitados), explicitamente
identificados como proposta; os campos históricos nulos não foram falsificados.

Evidência local: `.backups/sam/group_registration_refresh.json`. A consulta atual
não recupera informações já apagadas; futuras capturas e backups passam a
preservar as configurações enquanto estiverem disponíveis no SAM.


Nova cópia após o enriquecimento: `35ab4ad5-bc45-4b15-bbb1-7fac09fb0247`.
SHA-256: `50686e94cf14739e25ad6dc314b154d10e4bfd1b4e2769006edde76f76ffebef`.
A cópia foi reaberta e validada: 1.698 cadastros capturados, 1.615 completos,
quatro cadastros antigos da Vila enriquecidos e a proposta do piloto preservada.
O painel identifica quatro períodos encerrados e três turmas ativas na Vila.
A cópia anterior foi revalidada e seu checksum permaneceu intacto.
Validação final: 90 testes passaram; Django sem erros; JavaScript válido e ficha
com seis abas e acesso aos lançamentos dos 12 alunos conferida em DOM de teste.
