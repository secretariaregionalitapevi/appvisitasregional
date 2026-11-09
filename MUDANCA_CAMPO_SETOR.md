# Implementação de Campo de Seleção de Setor no Cadastro

## Resumo da Mudança

Foi adicionado um campo de seleção de setor (dropdown) na página de cadastro do APP_VISITAS_CCB. O usuário agora deve selecionar o setor em que irá atuar no momento do registro, em vez de ter um setor pré-atribuído automaticamente.

## Mudanças Realizadas

### 1. Frontend - Página de Cadastro (user-register-v3.html)

#### Campo de Seleção de Setor
- **Localização:** Entre o campo de "Pesquise sua Comum..." e o checkbox de "Termos de Uso"
- **Ícone:** Ícone de edifício/organização
- **Opções disponíveis:**
  - Musicalização
  - Música
  - Visitas
  - D.A.R.P.E
  - G.E.M

#### CSS Adicionado
```css
.register-field select{
  width:100%;
  min-width:0;
  height:46px;
  padding:0 14px;
  border:0!important;
  outline:0;
  background:transparent;
  color:#495057;
  font-size:13px;
  appearance:none;
  cursor:pointer;
}
.register-field select option{
  color:#495057;
  background:#fff;
}
.register-field select:focus{
  color:#495057;
}
```

#### JavaScript Modificado
- O formulário agora envia o campo `setor` junto com os outros dados
- Validação de campo obrigatório para o setor
- Exemplo: `setor:document.getElementById("setor").value.trim()`

### 2. Backend - Views (ColorAdminApp/views.py)

#### Validação de Setor
- Adicionada validação para aceitar apenas setores válidos
- Lista de setores válidos: `['Musicalização', 'Música', 'Visitas', 'D.A.R.P.E', 'G.E.M']`
- Retorna erro HTTP 400 se setor inválido

#### Dados Armazenados
- Campo `cadastro_origem_setor_selecionado`: Setor escolhido pelo usuário
- Campo `sector`: Definido para o setor selecionado (antes usava apenas `suggested_sector`)
- Campo `cadastro_origem_setor_sugerido`: Mantido para histórico

#### Payload Supabase (Auth)
```python
"data": {
    ...
    "cadastro_origem_setor_selecionado": setor_selecionado,
    "cadastro_origem_setor_sugerido": suggested_sector,
    ...
}
```

#### Payload Profile
```python
profile_payload = {
    ...
    "cadastro_origem_setor_selecionado": setor_selecionado,
    "cadastro_origem_setor_sugerido": suggested_sector,
    "sector": setor_selecionado,
    ...
}
```

#### Audit Log
- O setor selecionado é registrado em `log_audit()` como `setor_selecionado`

## Comportamento

### Antes da Mudança
- Usuario se registrava no APP_VISITAS, APP_CARTAS ou APP_DARPE
- O setor era atribuído automaticamente baseado na origem:
  - APP_DARPE → "D.A.R.P.E"
  - APP_CARTAS → "Música"
  - APP_VISITAS → "Visitas"

### Depois da Mudança
- Usuario **deve** selecionar o setor em que irá atuar
- O setor selecionado é armazenado explicitamente no banco
- Facilita auditorias e aprovações mais precisas
- O campo é obrigatório

## Setores Disponíveis

Baseado no APP_GLOBAL (controllers.js), os setores são:

| Setor | Representação |
|-------|---------------|
| Musicalização | Secretário(a) da Musicalização |
| Música | Secretário(a) da Música |
| Visitas | Secretário(a) de Visitas |
| D.A.R.P.E | Secretário(a) da D.A.R.P.E |
| G.E.M | Secretário(a) da G.E.M |

## Testes Realizados

✅ Campo adicionado no formulário HTML
✅ CSS aplicado corretamente
✅ JavaScript enviando o setor
✅ Validação backend implementada
✅ Dados sendo salvos no Supabase

## Arquivos Modificados

1. `ColorAdminApp/templates/pages/user-register-v3.html`
   - Adicionado campo select com opções de setores
   - Adicionado CSS para estilização
   - Atualizado JavaScript para enviar setor

2. `ColorAdminApp/views.py`
   - Adicionada validação de setor (linhas 569-578)
   - Atualizado payload de signup (linha 582-595)
   - Atualizado profile payload (linhas 617-631)
   - Atualizado audit log (linhas 682-687)

## Observações

- O campo é obrigatório e deve ser preenchido antes do envio
- O cadastro exibe apenas Musicalização, Música, Visitas, D.A.R.P.E e G.E.M; EBI, RJM e D.E.P.A.C são recusados pelo servidor
- O setor pode ser diferente do sugerido pela origem (APP_DARPE, APP_CARTAS, etc)
- Todos os dados de setor são armazenados no perfil do usuário no Supabase

## Aprovação e isolamento das pastas

- O middleware consulta o perfil no Supabase em toda requisição protegida e só libera uma conta com `status = approved`.
- Se não for possível confirmar o status no Supabase, a requisição é bloqueada com erro 503; uma indisponibilidade não concede acesso.
- Após a aprovação, o setor principal libera somente a pasta correspondente. As rotas de Visitas, Musicalização, D.A.R.P.E, G.E.M e Música são verificadas no servidor, inclusive APIs e URLs digitadas diretamente.
- G.E.M é uma pasta própria e não herda automaticamente a autorização da Musicalização. Pastas adicionais só podem ser concedidas por usuário global.
- Para habilitar concessões administrativas da pasta G.E.M em `user_module_access`, aplicar `scripts/migrations/050_gem_module_access.sql` no Supabase.
