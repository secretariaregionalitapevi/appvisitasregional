# Dashboard de Auditoria - Guia de Testes e Validação

## 🚀 Iniciando o Desenvolvimento Local

### 1. Preparar Ambiente
```bash
cd "C:\Users\Usuário\OneDrive\APLICATIVOS REGIONAL\APP_VISITAS_CCB"

# Verificar Python
python --version  # Deve ser 3.8+

# Instalar dependências (se necessário)
pip install -r requirements.txt

# Configurar variáveis de ambiente
# .env deve conter:
# SUPABASE_URL=https://...supabase.co
# SUPABASE_KEY=eyJ...
# DJANGO_SECRET_KEY=...
```

### 2. Iniciar Servidor
```bash
python manage.py runserver 0.0.0.0:8000
# Output esperado: Starting development server at http://127.0.0.1:8000/
```

### 3. Acessar Dashboard
```
Chrome/Firefox/Edge: http://localhost:8000/auditoria/modulos/
(Será redirecionado para /user/login-v1 se não autenticado)
```

## 🧪 Testes de Funcionalidade

### Teste 1: Layout e Design
- [ ] Breadcrumb visível: "Início > Auditoria > Módulos"
- [ ] Heading: "AUDITORIA DE MÓDULOS" com subtitle
- [ ] 6 abas de módulos visíveis e clicáveis
  - [ ] Ícones corretos (🎵 🤝 ✉️ 🚶 🎓 📖)
  - [ ] Nomes corretos (Musicalização, DARPE, Cartas, Visitas, SAM, GEM)
  - [ ] Aba "Musicalização" ativa por padrão
- [ ] 4 KPI cards visíveis
  - [ ] "Total de Eventos" (teal, #0d7377)
  - [ ] "Operadores Ativos" (purple, #6c5ce7)
  - [ ] "Período" (orange, #f59e0b)
  - [ ] "Seu Escopo" (cyan, #0891b2)
  - [ ] Cada card tem mini-bars horizontais
  - [ ] Ícones visíveis

### Teste 2: Seção de Filtros
- [ ] Campo "Recurso" dropdown (Todos, Aulas, Presença para Musicalização)
- [ ] Campo "Ação" dropdown (Todas, Criar, Atualizar, Deletar)
- [ ] Campo "Operador" input text (placeholder: "Nome parcial...")
- [ ] Campo "Período" dropdown
  - [ ] "Últimos 30 dias" (selecionado por padrão)
  - [ ] "Últimos 7 dias"
  - [ ] "Hoje"
  - [ ] "Todos"
- [ ] Botão "Buscar" azul com ícone 🔍
- [ ] Botão "Excel" branco com ícone 📊
- [ ] Botão "Limpar" branco com ícone 🗑️

### Teste 3: Tabela de Auditoria
- [ ] Heading: "EVENTOS DE AUDITORIA" com contador "0 registros"
- [ ] Colunas:
  - [ ] Tipo (badge colorida)
  - [ ] Ação (texto bold)
  - [ ] Operador (nome do usuário)
  - [ ] Data/Hora (formato DD/MM/YYYY HH:MM:SS)
  - [ ] Detalhes (texto pequeno)
- [ ] Linhas de exemplo carregam com dados reais (se existirem)
- [ ] Mensagem "Carregando..." com spinner quando buscar

### Teste 4: Alternância de Módulos
```
Ações:
1. Clicar na aba "DARPE"
2. Verificar se:
   - [ ] DARPE fica com background teal
   - [ ] Musicalização volta ao branco
   - [ ] Select "Recurso" atualiza para opções DARPE (Atendimentos)
   - [ ] Tabela recarrega com dados de DARPE
   - [ ] Badges na tabela ficam LARANJA (#fff3e0)
   - [ ] KPIs atualizam com números de DARPE

3. Repetir para: Cartas, Visitas, SAM, GEM
   - [ ] Cada módulo carrega seus dados específicos
   - [ ] Badges mudam de cor corretamente
   - [ ] Recursos dropdowns mostram opções corretas
```

### Teste 5: Filtros e Busca
```
1. Manter Musicalização selecionado
2. Clicar "Buscar" sem filtros
   - [ ] Tabela exibe todos os eventos dos últimos 30 dias
   - [ ] Contador mostra número de registros

3. Selecionar Ação = "Criar"
4. Clicar "Buscar"
   - [ ] Tabela mostra apenas eventos de CRIAÇÃO

5. Selecionar Ação = "Atualizar"
6. Clicar "Buscar"
   - [ ] Tabela mostra apenas eventos de ATUALIZAÇÃO

7. Digitar nome no "Operador" (ex: "João")
8. Clicar "Buscar"
   - [ ] Tabela mostra apenas eventos de usuários com "João" no nome

9. Mudar "Período" para "7 dias"
10. Clicar "Buscar"
    - [ ] Tabela mostra eventos dos últimos 7 dias apenas

11. Mudar "Período" para "Hoje"
12. Clicar "Buscar"
    - [ ] Tabela mostra apenas eventos de hoje
```

### Teste 6: Exportação para Excel
```
1. Com algum filtro ativo (ex: últimos 30 dias)
2. Clicar botão "Excel"
   - [ ] Arquivo é baixado automaticamente
   - [ ] Nome: Auditoria_musicalizacao_YYYY-MM-DD.csv
   - [ ] Abre no Excel com separação por ; (ponto-vírgula)
   - [ ] Headers: Tipo, Ação, Operador, Data/Hora, Detalhes
   - [ ] Dados coincidem com tabela exibida
   - [ ] Caracteres especiais (ç, ã, é) estão corretos (BOM marker)
```

### Teste 7: Botão Limpar
```
1. Aplicar múltiplos filtros:
   - [ ] Recurso = "Aulas"
   - [ ] Ação = "Criar"
   - [ ] Operador = "João"
   - [ ] Período = "7 dias"

2. Clicar botão "Limpar"
   - [ ] Recurso volta a "Todos"
   - [ ] Ação volta a "Todas"
   - [ ] Operador campo fica vazio
   - [ ] Período volta a "30 dias"
   - [ ] Tabela recarrega com dados padrão
```

### Teste 8: Responsividade
```
Desktop (1920x1080):
- [ ] 4 KPI cards em 1 linha
- [ ] 4 filtros em 1 linha
- [ ] Tabela com todas as colunas visíveis

Tablet (768x1024):
- [ ] 2 KPI cards por linha
- [ ] 2 filtros por linha
- [ ] Tabela com scroll horizontal
- [ ] Buttons em linha

Mobile (375x667):
- [ ] 1 KPI card por linha
- [ ] 1 filtro por linha
- [ ] Buttons em grid 2 colunas
- [ ] Tabela compactada
```

### Teste 9: Controle de Acesso
```
1. Logout do sistema
2. Tentar acessar /auditoria/modulos/ diretamente
   - [ ] Redireciona para /user/login-v1

3. Login com usuário Municipal
   - [ ] Vê apenas dados de sua municipalidade
   - [ ] Scope KPI mostra "MUNICIPAL"

4. Login com usuário Regional
   - [ ] Vê dados de toda região
   - [ ] Scope KPI mostra "REGIONAL"

5. Tentar acessar com usuário sem permissão
   - [ ] Recebe erro 403 Forbidden na API
```

### Teste 10: Tratamento de Erros
```
1. Desconectar internet
2. Clicar "Buscar"
   - [ ] Tabela mostra "⚠️ Erro ao carregar dados"
   - [ ] Console não tem erros uncaught (verificar DevTools)

3. Reconectar internet
4. Clicar "Buscar" novamente
   - [ ] Dados carregam normalmente
```

## 🔍 Validação de Dados Supabase

### Verificar Tabelas Existem
```sql
-- Execute no Supabase SQL Editor

SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name LIKE '%musicalizacao%';
-- Esperado: musicalizacao_aulas, musicalizacao_presenca

SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name LIKE '%darpe%';
-- Esperado: darpe_atendimentos

SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name LIKE '%cartas%';
-- Esperado: cartas_exames

SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name LIKE '%visitas%';
-- Esperado: visitas_apontamentos

SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name LIKE '%sam%';
-- Esperado: sam_audit_events

SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name LIKE '%gem%';
-- Esperado: gem_aulas, gem_turmas, etc
```

### Verificar Colunas de Auditoria
```sql
-- Musicalizacao Aulas
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'musicalizacao_aulas'
ORDER BY column_name;
-- Deve conter: created_by_name, created_by_email, created_at, 
--              updated_by_name, updated_by_email, updated_at

-- Verificar dados
SELECT COUNT(*) as total_registros FROM musicalizacao_aulas;
SELECT COUNT(DISTINCT created_by_name) as operadores 
FROM musicalizacao_aulas 
WHERE created_at > NOW() - INTERVAL '30 days';
```

## 📊 Teste de Performance

```bash
# 1. Abrir DevTools (F12)
# 2. Ir para aba "Performance" ou "Network"

# 3. Com tabela vazia
# Tempo esperado: <100ms

# 4. Com 100+ registros
# Tempo esperado: <500ms

# 5. Com todos os filtros aplicados
# Tempo esperado: <1000ms

# 6. Exportar para Excel
# Tempo esperado: <2s (geração local)
```

## 🐛 Debugging

### Console do Navegador (F12)
```javascript
// Verificar dados carregados
console.log('currentModule:', currentModule);
console.log('resourceMap:', resourceMap);

// Verificar última requisição
// Network tab → /api/auditoria/generic/
// Response: {records: [...], total_events: N, active_operators: N}

// Teste de requisição manual
fetch('/api/auditoria/generic/?module=musicalizacao&period=30')
  .then(r => r.json())
  .then(d => console.log('Response:', d));
```

### Logs do Django
```bash
# Terminal com servidor rodando deve mostrar:
# GET /api/auditoria/generic/?module=musicalizacao&period=30 HTTP/1.1" 200
# GET /auditoria/modulos/ HTTP/1.1" 200
# POST requests (se houver) com dados

# Se houver erro:
# ERROR: ... (verificar mensagem de erro no stdout)
```

### Verificar Arquivos
```bash
# Sintaxe Python
python -m py_compile ColorAdminApp/modules/audit_generic.py
python -m py_compile ColorAdminApp/modules/admin_views.py

# Sintaxe HTML (Django templates)
python manage.py template_finder

# URLs
python manage.py show_urls | grep auditoria

# Migrações
python manage.py showmigrations
```

## ✅ Checklist Final

- [ ] Layout e design corretos
- [ ] 6 módulos funcionando
- [ ] Filtros funcionam
- [ ] Exportação Excel funciona
- [ ] Responsividade OK
- [ ] Acesso controlado
- [ ] Sem erros no console
- [ ] Sem erros no Django
- [ ] Dados Supabase validados
- [ ] Performance OK (<1s para 100 registros)
- [ ] Testes automatizados (se aplicável)

## 🚀 Deploy para Produção

```bash
# 1. Últimos commits
git log --oneline -5

# 2. Push para main
git push origin main
# Vercel auto-deploy

# 3. Testar em produção
# https://app.regional-ccb.com.br/auditoria/modulos/

# 4. Monitorar logs
# Vercel Dashboard → Deployments → Logs

# 5. Se houver erro, rollback
git revert <commit-hash>
git push origin main
```

## 📞 Suporte

### Problemas Comuns

**"Nenhum evento encontrado"**
- Verificar se módulo tem dados em Supabase
- Verificar se user tem acesso ao módulo
- Verificar período (30 dias padrão)

**"Erro ao carregar dados"**
- Verificar conexão internet
- Verificar Supabase API key válida
- Verificar permissões do usuário

**"Badges com cores erradas"**
- Verificar CSS do arquivo auditoria_modulos.html
- Limpar cache do navegador (Ctrl+Shift+Del)

**"Tabela vazia mas KPI mostra dados"**
- Verificar estrutura de resposta da API
- Verificar JavaScript processando response corretamente
- Abrir DevTools → Network → verificar JSON

