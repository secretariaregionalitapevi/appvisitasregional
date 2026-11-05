# Biblioteca do D.A.R.P.E.

Menu D.A.R.P.E.: Documentos, Instrumentos e Setores.

- Documentos reúne todos os PDFs, com busca e filtro por pasta.
- Instrumentos apresenta a transcrição da matriz fornecida, organizada em quatro setores. O antigo setor 5 integra o 4; as restrições educacionais permanecem específicas e não herdam a permissão hospitalar.
- Setores informa os quatro campos de atendimento e os dados gerais fornecidos pela administração até outubro de 2026. Esses números são históricos, não indicadores calculados dos cadastros regionais.
- O PDF original permanece identificado como referência histórica com cinco setores; a orientação organizada em quatro setores está na página Instrumentos.

Gestores de escopo regional/global com acesso ao DARPE publicam PDFs de até 20 MB. Os demais usuários do módulo podem consultar e baixar. Não se admite arquivo inválido, criptografado ou com ações automáticas/arquivos anexos no catálogo do PDF. O armazenamento é privado no bucket Supabase `darpe-documentos`; o servidor autentica e autoriza cada download. A chave administrativa nunca é enviada ao navegador.

Instalação: executar `scripts/migrations/040_darpe_documentos.sql` no mesmo Supabase do sistema. A tabela `darpe_documentos` conserva título, pasta, descrição, nome original, tamanho, autor e data de publicação; RLS bloqueia acesso direto dos clientes. Fazer backup da tabela e dos objetos do bucket conjuntamente. A interface não altera nem exclui documentos já publicados.

## Revisão visual e atualizações periódicas

A matriz PDF mantém o cabeçalho e a composição do documento original por solicitação expressa: faixas por família, células de marcação e quatro setores. A interface usa o componente compartilhado de escopo, incluindo a comum.

Executar também `041_darpe_estatisticas_historico.sql`. Os dados estatísticos não ficam mais fixos no HTML. A gestão regional/global registra competência, cinco indicadores acumulados, fonte, distribuição e observações. Cada publicação é uma nova linha; uma revisão da mesma competência preserva a anterior. O banco impede UPDATE e DELETE no histórico. A curva usa apenas a versão mais recente de cada competência e permite consultar versões antigas. Sem competência anterior, mostra Base inicial; não estima variações.

## Gerenciador de arquivos

A biblioteca reutiliza a estrutura de `extra-file-manager.html` do Color Admin: painel, barra de ferramentas, árvore de pastas, breadcrumbs e tabela. Instalar `042_darpe_gerenciador_arquivos.sql`. As três pastas principais são fixas; gestores criam subpastas e podem renomeá-las.

Selecionar um arquivo habilita Visualizar, Baixar, Editar/substituir e Versões. Gestores podem alterar título, descrição, nome e pasta. Substituir o PDF envia um objeto novo; nunca sobrescreve o anterior. O histórico permite visualizar, baixar e restaurar uma publicação como nova versão. A edição compara a versão lida com a atual para detectar alterações concorrentes. Remover envia à lixeira, sem exclusão permanente; usuários de consulta não acessam arquivos arquivados. Alterações múltiplas são executadas individualmente e eventuais falhas indicam quantos arquivos foram concluídos.

Visualização é feita em iframe com PDF inline e SAMEORIGIN; o download permanece autenticado. O sistema edita os dados do documento e substitui o PDF; não modifica o texto interno de um PDF.
