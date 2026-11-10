# Teste do Dashboard de Auditoria

## Verificações Realizadas

### ✅ 1. Verificação de Código

```
OK: api_audit function found
OK: page function found
OK: auditoria keyword found in musicalizacao.py
OK: API route configured

All integration checks passed.
```

### ✅ 2. Compilação Python

```
Arquivo: ColorAdminApp/modules/musicalizacao.py
Status: Sem erros de sintaxe
Imports: Todos os módulos importam corretamente
```

### ✅ 3. Estrutura de Rotas

```
Path                              View                    Name
─────────────────────────────────────────────────────────────────
/musicalizacao/auditoria/         musicalizacao.page      musicalizacaoSection
/musicalizacao/api/auditoria/     musicalizacao.api_audit musicalizacaoAudit
```

## Instruções para Teste Manual

### Pré-requisitos
- Django server rodando localmente
- Usuário autenticado com acesso à pasta Musicalização
- Supabase configurado e acessível

### Teste 1: Acesso à Página

1. Abra o navegador (Externo - nunca localhost via Codex)
2. Navegue para: `http://127.0.0.1:8000/musicalizacao/auditoria/`
3. Esperado:
   - ✓ Página carrega sem erros
   - ✓ KPIs aparecem (podem estar em 0 ou carregando)
   - ✓ Filtros aparecem
   - ✓ Console do browser limpo (sem erros)

### Teste 2: Carregamento de Dados

1. Na página do dashboard, abra Developer Tools (F12)
2. Aba Network
3. Atualize a página (F5)
4. Procure por requisição `auditoria` (GET)
5. Esperado:
   - ✓ Request para `/musicalizacao/api/auditoria/` com status 200
   - ✓ Response contém JSON com structure:
     ```json
     {
       "results": {
         "aulas": [...],
         "presencas": [...]
       },
       "scope": {...},
       "filters": {...}
     }
     ```

### Teste 3: Filtros

1. Selecione um filtro (ex: "Últimos 7 dias")
2. Clique "Filtrar"
3. Esperado:
   - ✓ Tabela se atualiza
   - ✓ KPIs se atualizam
   - ✓ Sem erros no console

### Teste 4: Acesso Negado

1. Faça logout (se possível, remova cookie de sessão)
2. Tente acessar `/musicalizacao/auditoria/`
3. Esperado:
   - ✓ Erro 403 ou redirecionamento para login

### Teste 5: Escopos

1. Teste com diferentes perfis:
   - Regional (vê todos os registros)
   - Municipal (vê apenas do município)
   - Local (vê apenas do polo/comum)
2. Esperado:
   - ✓ Dados filtrados corretamente por escopo

## Verificação de Performance

### Requisição GET /musicalizacao/api/auditoria/

**Esperado**:
- Tempo de resposta: < 2 segundos (para até 100 registros)
- Tamanho da resposta: ~50-150 KB típico
- Conexão com Supabase: Estável

**Se lento**:
- Verificar conexão com Supabase
- Aumentar `limit` pode ajudar paginação
- Considerar adicionar índices em Supabase

## Deploy para Produção

### Antes de Fazer Deploy

1. ✓ Verificar que todos os testes passam
2. ✓ Testar localmente com dados reais
3. ✓ Verificar escopos de acesso funcionam
4. ✓ Revisar logs para erros

### Passos do Deploy

```bash
# 1. Commit foi feito?
git log --oneline | head -1
# Esperado: "Criacao do dashboard de auditoria para Musicalizacao"

# 2. Push para main
git push origin main

# 3. Vercel detecta automaticamente
# - Monitore em https://vercel.com/dashboard

# 4. Teste em produção
# https://seu-dominio/musicalizacao/auditoria/
```

### Validação Pós-Deploy

1. Acessar dashboard em produção
2. Verificar se dados aparecem
3. Testar filtros
4. Verificar logs (Vercel) para erros
5. Testar com diferentes perfis de usuário

## Checklist de Funcionalidades

### Dashboard

- [ ] Página carrega
- [ ] KPIs exibem valores corretos
- [ ] Filtros funcionam
- [ ] Tabela exibe eventos
- [ ] Datas formatadas em pt-BR
- [ ] Sem erros no console

### API

- [ ] GET /musicalizacao/api/auditoria/ retorna 200
- [ ] Filtra por resource
- [ ] Filtra por action
- [ ] Filtra por actor
- [ ] Filtra por dias
- [ ] Respeita escopo
- [ ] Retorna 403 para acesso negado
- [ ] Retorna 405 para método não permitido

### Segurança

- [ ] Apenas usuários autenticados veem dados
- [ ] Escopos de acesso respeitados
- [ ] Dados não vazam entre municípios
- [ ] Dados não vazam entre polos (coordenadores)

## Possíveis Problemas e Soluções

| Problema | Solução |
|----------|---------|
| KPIs mostram 0 | Verificar se há dados em Supabase nos últimos 30 dias |
| Tabela vazia | Aumentar período com filtro "Últimos 90 dias" ou "Último ano" |
| Erro 403 | Verificar permissões do usuário (precisa de acesso a Musicalização) |
| Erro 502 | Supabase offline - verificar status em supabase.com |
| Lentidão | Reduzir período ou limitar limite de registros |
| Dates incorretas | Verificar timezone do servidor |

## Rollback

Se houver problemas em produção:

```bash
# Reverter para commit anterior
git revert b440473

# Push para main
git push origin main

# Vercel faz deploy automaticamente
```

---

**Última atualização**: 2024-11-28  
**Status**: Pronto para teste e deploy  
**Responsável**: Validação manual do usuário
