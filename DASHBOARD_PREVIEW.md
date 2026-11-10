# Dashboard de Auditoria Centralizada - Visualização

## 📺 Estrutura Visual

### 1. **Breadcrumb & Heading**
```
[Início] > [Auditoria] > [Módulos]

AUDITORIA DE MÓDULOS
Rastreamento centralizado de operações em todos os módulos
```

### 2. **Module Selector Tabs**
```
┌─────────────────────────────────────────────────────────────┐
│ 🎵 Musicalização  | 🤝 DARPE | ✉️ Cartas | 🚶 Visitas | 🎓 SAM | 📖 GEM │
└─────────────────────────────────────────────────────────────┘
   └─ Active tab highlighted with teal border & background
```

### 3. **KPI Cards (Premium Stats)**
```
┌─────────────────────────────────────────────────────────────────┐
│
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  │ Total de Eventos │  │ Operadores Ativos│  │     Período      │  │   Seu Escopo     │
│  │  📊              │  │  👥              │  │  📅              │  │  🔒              │
│  │  (TEAL)          │  │  (PURPLE)        │  │  (ORANGE)        │  │  (CYAN)          │
│  │      0           │  │       0          │  │       30         │  │  REGIONAL        │
│  │ últimos 30 dias  │  │ realizaram       │  │ dias             │  │                  │
│  │                  │  │ alterações       │  │ selecionados     │  │                  │
│  │ ▂▅▃▇▄ (bars)     │  │ ▂▅▃▇▄ (bars)     │  │ ▂▅▃▇▄ (bars)     │  │ ▂▅▃▇▄ (bars)     │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  └──────────────────┘
│
└─────────────────────────────────────────────────────────────────┘
```

### 4. **Filter Section**
```
┌────────────────────────────────────────────────────────────────────────────────┐
│ Recurso: [Todos ▼]   | Ação: [Todas ▼]    | Operador: [___________]          │
│                      |                    |                                   │
│ Período: [30 dias ▼] | [🔍 Buscar] [📊 Excel] [🗑️ Limpar]                   │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 5. **Audit Events Table**

#### Musicalização:
```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ EVENTOS DE AUDITORIA (0 registros)                                                   │
├──────────────────────────────────────────────────────────────────────────────────────┤
│ Tipo                 │ Ação        │ Operador          │ Data/Hora          │ Detalhes  │
├──────────────────────┼─────────────┼───────────────────┼────────────────────┼───────────┤
│ [AULAS]              │ Criação     │ João Silva        │ 15/01/2026 10:30   │ Registro… │
│ [PRESENÇA]           │ Atualização │ Maria Santos      │ 14/01/2026 14:15   │ Registro… │
│ [AULAS]              │ Criação     │ Pedro Oliveira    │ 13/01/2026 09:00   │ Registro… │
│                      │             │                   │                    │           │
│ Nenhum evento encontrado quando filtros não retornam dados                          │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

#### DARPE:
```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ EVENTOS DE AUDITORIA (0 registros)                                                   │
├──────────────────────────────────────────────────────────────────────────────────────┤
│ Tipo                 │ Ação        │ Operador          │ Data/Hora          │ Detalhes  │
├──────────────────────┼─────────────┼───────────────────┼────────────────────┼───────────┤
│ [ATENDIMENTOS]       │ Criação     │ Ana Costa         │ 12/01/2026 08:45   │ Registro… │
│ [ATENDIMENTOS]       │ Atualização │ Carlos Mendes     │ 11/01/2026 16:20   │ Registro… │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

## 🎨 Cores por Módulo

| Módulo | Cor Principal | Badge Background | Badge Text Color |
|--------|---|---|---|
| Musicalização | #0d7377 (Teal) | #e8f8f4 | #087d69 |
| DARPE | #ff6b35 (Orange) | #fff3e0 | #e65100 |
| Cartas | #e91e63 (Pink) | #fce4ec | #c2185b |
| Visitas | #0891b2 (Cyan) | #e1f5fe | #0277bd |
| SAM | #7b1fa2 (Purple) | #f3e5f5 | #7b1fa2 |
| GEM | #0050b3 (Blue) | #ebf5ff | #0050b3 |

## 📱 Responsividade

### Desktop (≥1200px):
- 4 KPI cards em 1 linha
- 4 filtros em 1 linha
- Tabela com scroll horizontal

### Tablet (768px - 1199px):
- 2 KPI cards por linha
- 2 filtros por linha
- Tabela com scroll

### Mobile (<768px):
- 1 KPI card por linha
- 1 filtro por linha
- Tabela compactada
- Buttons em grid 2 colunas

## 🔄 Interações

### Module Tab Click:
1. Tab se torna ativa (borda/background teal)
2. resourceMap atualiza select de Recursos
3. `loadData()` é chamado automaticamente
4. Tabela carrega eventos do novo módulo
5. KPIs atualizam com dados do módulo

### Filtro Buscar:
1. Spinner aparece na tabela
2. Requisição GET → `/api/auditoria/generic/?module=musicalizacao&resource=&action=&operator=&period=30`
3. Resposta retorna `{records: [...], total_events: N, active_operators: N, scope: "REGIONAL"}`
4. Tabela popula com registros
5. KPIs atualizam
6. Record count badge mostra "X registros"

### Exportar Excel:
1. Clique em botão "📊 Excel"
2. Gera CSV com BOM marker
3. Headers: Tipo, Ação, Operador, Data/Hora, Detalhes
4. Arquivo: `Auditoria_musicalizacao_2026-01-15.csv`
5. Download automático no navegador

### Limpar Filtros:
1. Todos os inputs voltam aos valores padrão
2. `loadData()` é chamado
3. Tabela carrega dados sem filtros
4. KPIs mostram totals gerais do módulo

## 🚨 Estados de Erro

### Servidor indisponível:
```
┌──────────────────────────────────────────────────┐
│ ⚠️ Erro ao carregar dados                        │
└──────────────────────────────────────────────────┘
```

### Nenhum dado encontrado:
```
┌──────────────────────────────────────────────────┐
│ Nenhum evento encontrado                         │
└──────────────────────────────────────────────────┘
```

### Carregando:
```
┌──────────────────────────────────────────────────┐
│ ⏳ Carregando…                                    │
└──────────────────────────────────────────────────┘
```

## 📊 Dados de Exemplo

### Musicalização - Aulas:
```
Tipo: AULAS
Ação: Criação
Operador: João Silva
Data/Hora: 15/01/2026 10:30:45
Detalhes: Registro ID: 550e8400-e29b-41d4-a716-446655440000
```

### DARPE - Atendimentos:
```
Tipo: ATENDIMENTOS
Ação: Atualização
Operador: Ana Costa
Data/Hora: 12/01/2026 08:45:20
Detalhes: Registro ID: 6ba7b810-9dad-11d1-80b4-00c04fd430c8
```

## 🔐 Acesso e Permissões

- Requer autenticação (redireciona para login se não autenticado)
- Requer `can_access_module()` para visualizar dados do módulo
- Respeita `can_access()` para filtrar por escopo (REGIONAL/MUNICIPAL)
- Usuário Municipal vê apenas sua municipalidade
- Usuário Regional vê dados de toda região

## ✅ Checklist de Funcionalidades

- [x] Abas de módulos interativas
- [x] KPI cards com mini-bars
- [x] Filtros por recurso/ação/operador/período
- [x] Tabela de eventos com paginação básica
- [x] Badges coloridas por módulo
- [x] Export para Excel/CSV
- [x] Carregamento dinâmico (AJAX)
- [x] Estados de erro e carregamento
- [x] Responsivo para mobile/tablet
- [x] Controle de acesso integrado
- [x] Data formatada pt-BR
- [x] Contador de registros

