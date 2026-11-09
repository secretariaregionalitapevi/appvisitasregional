# Atendimentos DARPE e APP_DARPE

## Primeira versão

A administração usa `/darpe/atendimentos/`, no menu D.A.R.P.E → Atendimentos. O painel acompanha o padrão de Musicalização: cabeçalho com escopo, filtros de ano/mês/período/município/comum/setor, quatro indicadores, leitura de gestão, evolução mensal, distribuição setorial, resumo municipal, atendentes responsáveis e tabela paginada dos lançamentos. Excel e PDF utilizam os mesmos filtros e o padrão institucional.
O aplicativo instalável em `../APP_DARPE` segue a estrutura Node e a identidade do APP_VISITAS_MOBILE. A seleção por busca de nomes segue a interação do APP_CARTAS, com uma fonte exclusiva: `darpe_cadastro`.

No mobile, `/` é a página da equipe no padrão do Visitas: cabeçalho compacto, saudação, município/comum/data, três resumos e cartões de atendimentos por período do dia. Os cartões distinguem os quatro setores por badge, identificam o local com ícone neutro e exibem links para WhatsApp e telefone somente quando os números foram informados. A ação fixa **Lançar atendimento** abre `/atendimento`, com a papeleta inteira visível. Atendente, orações, músicos, organistas, colaboradores e irmão da palavra têm seleções identificadas. A consulta de uma papeleta registrada usa `/atendimento?registro=UUID`, permite editar os campos e gerar o PDF individual. O formulário envia ao mesmo servidor principal e retorna à data lançada após a confirmação.

### Mapeamento da papeleta

| Campo original | Registro digital |
|---|---|
| Data / horário | Data, início e término |
| Local | Instituição/unidade atendida |
| Contatos | WhatsApp e outro telefone opcionais, registrados sem inferência |
| Atendente | Exatamente um cadastro ativo com `darpe_atendente` |
| Orações | Uma ou mais pessoas cadastradas como atendente, colaborador ou ministério |
| Músicos | Cadastros ativos com `darpe_musico` ou `darpe_organista`, selecionados por função |
| Hinos | Lista de números entre 1 e 480 |
| Palavra | Referência bíblica em texto |
| Irmão | Cadastro ativo com função atendente ou ministério |
| Participação | Texto para discriminar internos, visitantes, músicos e demais participantes |
| Obs. | Observações |
| Pedidos de oração | Quantidades: enfermidades, acidentados, tribulações, famílias, causas, testemunhados e viagens |
| Família(s): todas | Opção exclusiva para famílias, alternativa à quantidade |

Acrescentam-se setor (quatro setores oficiais), município e comum responsáveis para aplicar o escopo territorial. Colaboradores e organistas têm identificação própria na equipe. Não se usam os nomes manuscritos da foto como dados de demonstração.

## Fluxo e segurança

O operador preenche, pesquisa a equipe e registra a papeleta. A página lista atendimentos por data/setor e abre os detalhes. A inclusão e a edição salvam os campos e a equipe em uma única operação; nomes são obtidos novamente no servidor, nunca aceitos do navegador. Pessoas inativas, desconhecidas e com função divergente são recusadas. O PDF individual segue o padrão institucional de exportação e inclui os contatos registrados.

O APP_DARPE faz login no mesmo Supabase e encaminha o Bearer à API `/darpe/mobile/api/`. O Django valida o token, consulta o perfil aprovado atual e verifica a pasta DARPE e o escopo. A exceção ao middleware de sessão e ao CSRF está restrita à rota Bearer; uma sessão por cookie nunca autentica essa rota. O mobile não precisa da chave service_role.

As buscas retornam apenas ID, nome, comum, município e instrumento. Não consultam SAM, APP_CARTAS ou cadastro geral. A listagem, seleção e gravação respeitam o escopo no servidor. Não há cache offline de tokens ou papeletas no service worker. A sessão usa a expiração/inatividade do projeto mobile de referência.

Cada submissão tem UUID mantido durante a repetição após falha de rede. Conflito de UUID só retorna o registro existente quando pertence ao mesmo operador e escopo. Uma papeleta registrada preserva operador, instante e nomes da equipe. Nesta etapa, o fluxo disponibiliza inclusão e consulta; correções e cancelamento de registros precisarão de histórico próprio antes de serem habilitados.

## Instalar

1. Aplicar, em ordem, `scripts/migrations/047_darpe_atendimentos.sql`, `scripts/migrations/048_darpe_papeletas_gestao.sql` e `scripts/migrations/049_darpe_papeletas_contatos.sql` no mesmo Supabase do sistema principal. As papeletas ficam em `darpe_papeletas`, privada, com RLS e sem acesso `anon/authenticated`. A tabela legada `darpe_atendimentos` (campos `data_atendimento`, `local_nome` etc.) permanece intacta. As migrações podem ser repetidas; se uma instalação nova recebeu papeletas na estrutura canônica com o nome antigo, elas são copiadas sem sobrescrever IDs existentes.
2. Publicar a atualização do projeto principal.
3. Configurar `APP_DARPE/.env` a partir de `.env.example` com as chaves públicas do mesmo Supabase, `PRINCIPAL_URL` e a origem pública do mobile.
4. Executar `npm test` e `npm run check` no APP_DARPE. Publicar em HTTPS para instalação mobile.

## Identidade e validação

O painel principal reutiliza a composição de Musicalização: fundo claro, cabeçalho azul/petróleo/verde, escopo à direita, barra branca de filtros, indicadores com minigráficos e painéis de gestão. O aplicativo mobile tem sua própria página e mantém a identidade do APP_VISITAS_MOBILE. A tipografia acompanha cada projeto. O formulário segue a ordem da papeleta e usa alvos de toque de 44 px. Feedback reutiliza `AppFeedback`, com painel central e fundo desfocado. Cancelar usa vermelho e `fa-xmark`.

Os testes verificam campos, funções, pessoas externas/inativas, escopo, aprovação, Bearer, repetição de submissão, proteção do proxy, arquivos estáticos, filtros de gestão e exportações. Um PDF real com três páginas e uma planilha são gerados para conferir cabeçalho, datas, paginação e aproveitamento da largura. A validação integrada com o banco depende da aplicação da migração.

## Aprovação de acesso DARPE

O botão Criar conta do APP_DARPE usa `/user/cadastro?origem=darpe` no portal principal. O perfil é criado pendente, com origem Aplicativo DARPE e pasta D.A.R.P.E. O cadastro não concede acesso antes da aprovação.

Em Auditoria, abra o usuário em Pendentes ou Usuários, selecione a pasta D.A.R.P.E, confira município e comum, escolha o nível Local (comum), Municipal (município) ou Regional (região), defina Aprovado e salve. Somente administradores globais podem liberar ou revogar pastas. A concessão e a aprovação são registradas na auditoria existente. Pastas adicionais permanecem independentes do nível territorial.

A tabela de concessões e o suporte à pasta DARPE já fazem parte da migração 045; esta correção não exige nova migração nem libera automaticamente usuários existentes.
