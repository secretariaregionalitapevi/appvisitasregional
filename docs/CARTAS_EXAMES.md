# Cartas de Exames

O menu **Música → Cartas de Exames** (`/musica/cartas-exames/`) acompanha as cartas emitidas no APP_CARTAS, usando o mesmo Supabase. A lista é atualizada automaticamente a cada 45 segundos e também pelo botão Atualizar.

## Cartas e resultados

Uma carta com PDF emitido entra como **Aguardando confirmação**. Preencher a carta não aprova o candidato. O secretário da música, dentro do seu escopo, ou a gestão regional pode conferir o resultado no painel. O nome do responsável, a data, as observações e a versão ficam conservados.

Ao confirmar, a função `cartas_confirmar_resultado` bloqueia a carta e atualiza, em uma transação, o resultado da carta, o registro individual de Exames e Testes e a contagem compartilhada. A chave de idempotência impede duplicação do mesmo exame. Somente **APROVADO** soma na coluna da modalidade correspondente. Voltar para pendente, ausência ou retorno ao ciclo retira essa aprovação do total. Versões divergentes exigem atualizar a tela antes de confirmar novamente.

Os agrupamentos permanecem Itapevi; Jandira; Cotia/Caucaia/VGP; Santana/Pirapora. A autorização territorial é aplicada antes da consulta, confirmação e exportação. A integração usa os registros existentes de exames, sem executar os fluxos externos n8n. O avanço do nível cadastral não é alterado automaticamente por este novo painel.

## Relatório

PDF e Excel usam exatamente o recorte da lista: município/administração, músico/organista, modalidade, evento, mês, período, resultado e busca. O PDF conserva a organização da referência recebida por modalidade, com número, nome, comum, instrumento e observação; adiciona o cabeçalho institucional obrigatório, identificação de quem imprimiu, emissão e paginação. O Excel segue o mesmo padrão institucional, com filtros, cabeçalho fixo e impressão ajustada.

A relação é gerada com os registros atuais no momento do download. “Cartas emitidas” representa PDFs gerados; não presume entrega física de documentos. As cartas individuais permanecem em armazenamento privado e são abertas no painel mediante autorização territorial.

## Ministério e assistência

`cartas_ministerio_comuns` registra os responsáveis pela assinatura por código da comum. A relação enviada é a fonte do ancião que assina, mesmo que ele dê assistência e pertença a outra congregação. Isso não altera seu cadastro ministerial de origem.

O item 3 do APP_CARTAS é obrigatório. Ancião/assistência, encarregado regional e encarregado local devem estar cadastrados. Quando a relação não informa cooperador, usa-se o texto autorizado **Sem Cooperador do Ofício**. Uma relação sem os demais responsáveis bloqueia a emissão e aparece incompleta no painel. Cada carta conserva uma cópia dos responsáveis selecionados: atualizar a relação não reescreve cartas anteriores.

A gestão regional pode atualizar a relação pelo botão Importar relação. Também existe o comando:

```powershell
python manage.py import_cartas_ministerio "caminho\relação.xlsx"
python manage.py import_cartas_ministerio "caminho\relação.xlsx" --commit
```

O primeiro comando apenas confere. A importação grava código da comum, nomes, município, linha e hash da fonte; não importa telefones nem altera `ministerio_regional`. Comuns duplicadas são recusadas. Inclusões e alterações ficam em `cartas_ministerio_auditoria`.

## Instalação e validação

Aplicar `scripts/migrations/039_cartas_exames_painel.sql`, que inclui a estrutura compartilhada do APP_CARTAS. A migração e a importação inicial já foram executadas neste ambiente. Foram importadas 183 comuns; BR-21-1644 - Parque Jaguari precisa completar os responsáveis.

Foram validados os filtros, separação de cartas e aprovações, agrupamentos, assinatura por assistência, permissões, PDF/Excel e prevenção de fórmulas em valores do Excel. A confirmação real foi testada em transação com rollback, incluindo aprovação repetida, reversão e auditoria. Nenhuma aprovação fictícia foi conservada.

## Auditoria dos aplicativos

O APP_CARTAS registra no `audit_logs` os logins, a emissão de cartas e as alterações de recebimento municipal. Uma emissão pública é identificada como **Emissão pública sem login**, sem atribuir um usuário fictício; o banco deve aceitar `user_id` nulo para esse evento. As auditorias próprias de emissão e recebimento continuam existindo.

O APP_EXAMES registra o login e o lançamento de exames no mesmo painel. O lançamento exige token válido e perfil aprovado; o nome do responsável é definido no servidor, não pelo formulário. Os antigos endpoints de cadastro público de criança e monitor e o cadastro de perfil não são cobertos por essa integração.

As operações e a escrita na auditoria central são separadas. Se o evento falhar após a gravação, o aplicativo avisa que a operação já ocorreu; verifique os dados e informe a administração antes de tentar novamente. Não há garantia de atomicidade ou recuperação automática de eventos faltantes. Para ativar a integração, publique as alterações do painel e dos aplicativos correspondentes, usando o mesmo Supabase e uma tabela `audit_logs` compatível. Não há migração adicional incluída nesta alteração.
