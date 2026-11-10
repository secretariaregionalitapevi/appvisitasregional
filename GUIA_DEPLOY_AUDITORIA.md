# Guia de Deploy - Dashboard de Auditoria

## 🎯 Objetivo

Colocar o Dashboard de Auditoria de Musicalização em produção na Vercel.

---

## ✅ Pré-Deploy Checklist

- [x] Código foi testado localmente
- [x] Sintaxe Python validada
- [x] Integração de rotas verificada
- [x] Segurança de acesso implementada
- [x] Commit foi feito: `b440473`
- [x] Documentação foi criada

---

## 🚀 Procedimento de Deploy

### Opção 1: Deploy via Git (Recomendado)

**Passo 1: Verificar Status**
```bash
cd "C:\Users\Usuário\OneDrive\APLICATIVOS REGIONAL\APP_VISITAS_CCB"

# Verificar branch
git branch
# Esperado: * main

# Verificar commits
git log --oneline -3
# Esperado: b440473 Criacao do dashboard de auditoria para Musicalizacao
```

**Passo 2: Fazer Push**
```bash
# Push para origem (Vercel detecta automaticamente)
git push origin main

# Esperado:
# Enumerating objects...
# Writing objects...
# remote: Vercel Deployment triggered
```

**Passo 3: Monitorar Deploy**
- Acesse: https://vercel.com/dashboard
- Procure por `APP_VISITAS_CCB` ou repositório
- Aguarde conclusão (geralmente 2-5 minutos)
- Status: ✅ Ready (verde)

**Passo 4: Teste em Produção**
```
URL: https://seu-dominio/musicalizacao/auditoria/
```

---

### Opção 2: Deploy Manual (Se Git falhar)

**Via Vercel CLI:**
```bash
# Instalar Vercel CLI (se não tiver)
npm install -g vercel

# Fazer deploy
vercel deploy --prod

# Seguir prompts
```

**Via Vercel Web:**
1. Login em https://vercel.com
2. Selecione projeto
3. Clique "Redeploy" (ou mergue PR se houver)
4. Aguarde conclusão

---

## 📊 O Que Muda em Produção

### Novo:
```
GET  /musicalizacao/auditoria/
GET  /musicalizacao/api/auditoria/
```

### Funcionalidade:
- ✅ Dashboard acessível para usuários autenticados
- ✅ API retorna dados auditados do Supabase
- ✅ Escopos de acesso respeitados

### Arquivos Afetados:
- `ColorAdminApp/modules/musicalizacao.py` (+118 linhas)
- `ColorAdminApp/urls.py` (+1 linha)
- `ColorAdminApp/templates/pages/musicalizacao_auditoria.html` (novo, +403 linhas)

---

## ✅ Validação Pós-Deploy

### 1. Verificar Acesso

**Teste Público** (sem autenticação):
```
GET https://seu-dominio/musicalizacao/auditoria/
Esperado: Redirecionamento para login (301/302) ou erro 403
```

**Teste Autenticado** (com usuário válido):
```
GET https://seu-dominio/musicalizacao/auditoria/
Esperado: Página carrega com dashboard (200)
```

### 2. Verificar API

```bash
# Substitua seu-dominio-aqui
curl -H "Cookie: sessionid=YOUR_SESSION_ID" \
  "https://seu-dominio/musicalizacao/api/auditoria/?days=30&limit=10"

# Esperado:
# {
#   "results": {
#     "aulas": [...],
#     "presencas": [...]
#   },
#   "scope": {...},
#   "filters": {...}
# }
```

### 3. Verificar Dados

1. Abra DevTools (F12)
2. Aba Network
3. Atualize página
4. Procure por requisição `auditoria`
5. Verifique response (deve conter dados ou array vazio)

### 4. Verificar Erros

**Console do Browser:**
- Não deve haver erros em vermelho
- Avisos (amarelo) são normais

**Vercel Logs:**
- https://vercel.com/dashboard → Projeto → Deployments → Ver logs
- Procure por erros 5xx
- Verifique requestTimeout ou erros do Supabase

---

## 🔍 Troubleshooting

### Erro 403 Forbidden
**Causa**: Usuário sem acesso à pasta Musicalização
**Solução**: 
- Verificar permissões no sistema (user_profile)
- Testar com outro usuário (regional ou admin)

### Erro 404 Not Found
**Causa**: Rota não registrada ou deploy incompleto
**Solução**:
- Aguardar 5 minutos após deploy
- Verificar commit foi feito com sucesso
- Fazer redeploy manual

### Erro 502 Bad Gateway
**Causa**: Problema com conexão Supabase
**Solução**:
- Verificar status Supabase em supabase.com
- Verificar SUPABASE_URL e chave API em .env
- Testar API diretamente: `curl https://seu-supabase.supabase.co/rest/v1/musicalizacao_aulas`

### Dados não aparecem
**Causa**: Sem dados de auditoria no período (< 30 dias)
**Solução**:
- Alterar filtro para período maior (90 dias, 1 ano)
- Criar dados de teste (POST em /musicalizacao/api/aulas/)
- Verificar dados em Supabase diretamente

### Lentidão
**Causa**: Muitos dados ou conexão lenta
**Solução**:
- Reduzir `limit` em filtro (padrão 50)
- Reduzir período de busca
- Verificar performance Supabase
- Adicionar índices em colunas de auditoria (DBA)

---

## 📋 Checklist de Validação Pós-Deploy

### Funcionalidades
- [ ] Dashboard acessível em `/musicalizacao/auditoria/`
- [ ] API respondendo em `/musicalizacao/api/auditoria/`
- [ ] KPIs exibem valores corretos
- [ ] Filtros funcionam
- [ ] Tabela exibe eventos
- [ ] Datas em formato pt-BR
- [ ] Paginação funciona

### Segurança
- [ ] Acesso não autenticado retorna erro (403/redirect)
- [ ] Escopos respeitados (testar diferentes perfis)
- [ ] Dados não vazam entre municípios
- [ ] Dados não vazam entre polos
- [ ] Console sem erros JavaScript

### Performance
- [ ] Tempo de resposta API < 2s
- [ ] Página carrega em < 3s
- [ ] Suporta 100+ registros sem lag
- [ ] Mobile responsivo (testar em celular)

### Logs
- [ ] Sem erros 5xx em Vercel
- [ ] Sem timeouts
- [ ] Sem erros de autenticação Supabase

---

## 🔄 Rollback (Se Necessário)

Se o deploy causar problemas:

```bash
# Revert último commit
git revert b440473

# Push para desfazer
git push origin main

# Vercel faz deploy do revert automaticamente
# Página volta ao estado anterior em ~2 minutos
```

**Nota**: O revert mantém o commit no histórico (Git best practice)

---

## 📞 Suporte Pós-Deploy

### Checklist de Problemas

Se tiver problema, verifique:
1. [ ] Vercel deployment status (verde?)
2. [ ] Supabase status online?
3. [ ] Usuário tem permissão na pasta?
4. [ ] Dados existem no período selecionado?
5. [ ] DevTools console sem erros?
6. [ ] Network tab mostra requisição 200?

### Contactar
- Revisar logs Vercel
- Revisar logs Supabase
- Verificar `SECURITY_DEPLOYMENT.md` para configs
- Considerar rollback se tudo falhar

---

## 📊 Métricas Esperadas

| Métrica | Esperado | Máximo |
|---------|----------|--------|
| Tempo da página | < 1s | 3s |
| API Response | < 1s | 2s |
| Bundle size | ~50KB | 200KB |
| Erro 4xx | 0% | 1% |
| Erro 5xx | 0% | 0.1% |

---

## ✨ Depois que Estiver Live

1. **Monitorar Logs** por 24-48 horas
2. **Coletar Feedback** de usuários
3. **Documentar Learnings**
4. **Planejar Melhorias** (cache, export, etc)

---

## 🎉 Status Atual

| Item | Status |
|------|--------|
| Código | ✅ Pronto |
| Testes | ✅ Passou |
| Git | ✅ Commitado |
| Docs | ✅ Criada |
| Deploy | 🚀 **Aguardando Push** |

**Próximo Passo**: `git push origin main`

---

**Versão do Guia**: 1.0  
**Data**: 2024-11-28  
**Responsável**: Você (usuário)
