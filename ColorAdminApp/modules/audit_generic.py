"""Sistema centralizado de auditoria para todos os módulos.

Fornece funções para consultar, normalizar, enriquecer e apresentar a trilha de
auditoria consolidada com alta fidelidade semântica para todos os módulos do sistema.
"""
import concurrent.futures
from datetime import datetime, timedelta, timezone
import logging
import re
import requests
from zoneinfo import ZoneInfo
from django.conf import settings
from django.http import JsonResponse
from .access_control import _norm, can_access, common_catalog, service_headers, user_scope
from .module_access import can_access_module, is_global

logger = logging.getLogger(__name__)
SAO_PAULO_TIME_ZONE = ZoneInfo("America/Sao_Paulo")

# Configuração dos módulos com mapeamento rico de metadados
MODULE_METADATA = {
    "musicalizacao": {
        "display_name": "Musicalização Infantil",
        "icon": "fa-music",
        "badge_class": "badge-musicalizacao",
        "badge_bg": "#e8f8f4",
        "badge_color": "#087d69",
    },
    "cartas": {
        "display_name": "Cartas de Exames",
        "icon": "fa-envelope-open-text",
        "badge_class": "badge-cartas",
        "badge_bg": "#fce4ec",
        "badge_color": "#c2185b",
    },
    "visitas": {
        "display_name": "Programa de Visitas",
        "icon": "fa-person-walking",
        "badge_class": "badge-visitas",
        "badge_bg": "#e1f5fe",
        "badge_color": "#0277bd",
    },
    "darpe": {
        "display_name": "DARPE Atendimentos",
        "icon": "fa-handshake-angle",
        "badge_class": "badge-darpe",
        "badge_bg": "#fff3e0",
        "badge_color": "#e65100",
    },
    "sam": {
        "display_name": "Histórico SAM",
        "icon": "fa-graduation-cap",
        "badge_class": "badge-sam",
        "badge_bg": "#f3e5f5",
        "badge_color": "#7b1fa2",
    },
    "gem": {
        "display_name": "GEM Educação Musical",
        "icon": "fa-book-open-reader",
        "badge_class": "badge-gem",
        "badge_bg": "#ebf5ff",
        "badge_color": "#0050b3",
    },
    "admin": {
        "display_name": "Acessos & Segurança",
        "icon": "fa-shield-halved",
        "badge_class": "badge-admin",
        "badge_bg": "#f0f2f5",
        "badge_color": "#334155",
    },
}

OPERATOR_NAME_ALIASES = {
    _norm("Ricardo Grangeiro"): "Ricardo Grangeiro",
    _norm("Ricardo Grangieiro"): "Ricardo Grangeiro",
}


def clean_common(name):
    """Preserva a identificação oficial da comum, incluindo seu código BR."""
    if not name:
        return ""
    return str(name).strip()


def canonical_common(name):
    """Completa nomes sem código com o cadastro oficial de comuns."""
    common = clean_common(name)
    if not common or re.match(r"^BR-\d+-\d+\s*-\s*", common, flags=re.IGNORECASE):
        return common

    normalized_common = _norm(common)
    for catalog_item in common_catalog():
        official_common = clean_common(catalog_item.get("comum"))
        official_name = re.sub(
            r"^BR-\d+-\d+\s*-\s*", "", official_common, flags=re.IGNORECASE
        )
        if normalized_common in {_norm(official_common), _norm(official_name)}:
            return official_common
    return common


def canonical_operator_name(name):
    """Exibe aliases conhecidos sob o nome padronizado do operador."""
    display_name = str(name or "").strip()
    return OPERATOR_NAME_ALIASES.get(_norm(display_name), display_name)

def parse_iso(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

def format_datetime_br(iso_str):
    dt = parse_iso(iso_str)
    if not dt:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(SAO_PAULO_TIME_ZONE).strftime("%d/%m/%Y %H:%M")

def format_date_br(date_val):
    if not date_val:
        return "—"
    try:
        s = str(date_val)[:10]
        parts = s.split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
        return s
    except (TypeError, ValueError, IndexError):
        return str(date_val)

def compute_relative_time(iso_str, now_ref=None):
    dt = parse_iso(iso_str)
    if not dt:
        return ""
    if now_ref is None:
        now_ref = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now_ref - dt
    total_seconds = max(0, int(diff.total_seconds()))
    if total_seconds < 60:
        return "agora mesmo"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"há {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"há {hours} h"
    days = hours // 24
    if days == 1:
        return "ontem"
    if days < 30:
        return f"há {days} dias"
    months = days // 30
    return f"há {months} {'mês' if months == 1 else 'meses'}"

def get_action_badge_meta(action_type):
    act = str(action_type or "").upper()
    if act in {"CREATE", "CRIACAO", "CRIAR"}:
        return {"code": "CREATE", "label": "Criação", "class": "badge-action-create", "color": "#16a34a", "bg": "#dcfce7"}
    if act in {"UPDATE", "ATUALIZACAO", "ATUALIZAR"}:
        return {"code": "UPDATE", "label": "Atualização", "class": "badge-action-update", "color": "#2563eb", "bg": "#dbeafe"}
    if act in {"DELETE", "EXCLUSAO", "EXCLUIR"}:
        return {"code": "DELETE", "label": "Exclusão", "class": "badge-action-delete", "color": "#dc2626", "bg": "#fee2e2"}
    if act in {"APPROVE", "APROVACAO", "APROVAR"}:
        return {"code": "APPROVE", "label": "Aprovação", "class": "badge-action-approve", "color": "#0d9488", "bg": "#ccfbf1"}
    if act in {"REJECT", "REJEICAO", "REJEITAR"}:
        return {"code": "REJECT", "label": "Rejeição", "class": "badge-action-reject", "color": "#ea580c", "bg": "#ffedd5"}
    if act in {"ACCESS", "LOGIN", "ACESSO"}:
        return {"code": "ACCESS", "label": "Acesso", "class": "badge-action-access", "color": "#7c3aed", "bg": "#ede9fe"}
    if act in {"EXPORT", "EXPORTACAO"}:
        return {"code": "EXPORT", "label": "Exportação", "class": "badge-action-export", "color": "#475569", "bg": "#f1f5f9"}
    return {"code": "OPERATION", "label": act.replace("_", " ").title(), "class": "badge-action-other", "color": "#64748b", "bg": "#f8fafc"}


# ==============================================================================
# Coletores especializados por módulo com descrições semânticas ricas
# ==============================================================================

def fetch_table(table, params):
    try:
        url = f"{settings.SUPABASE_URL}/rest/v1/{table}"
        resp = requests.get(url, headers=service_headers(), params=params, timeout=12)
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception as exc:
        logger.warning("Falha ao consultar tabela %s: %s", table, exc)
        return []

def collect_musicalizacao(cutoff_iso, limit=200):
    records = []
    # 1. Aulas / Atividades
    aulas = fetch_table("musicalizacao_aulas", {
        "select": "id,data_aula,cidade,polo,nome_atividade,meninos_presentes,meninas_presentes,instrutores_presentes,observacoes,created_by_name,created_by_email,created_at,updated_by_name,updated_by_email",
        "created_at": f"gte.{cutoff_iso}",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    for r in aulas:
        polo_name = clean_common(r.get("polo"))
        cidade = r.get("cidade") or ""
        m = r.get("meninos_presentes") or 0
        f = r.get("meninas_presentes") or 0
        tot = m + f
        instr = r.get("instrutores_presentes") or 0
        data_fmt = format_date_br(r.get("data_aula"))
        nome_atv = r.get("nome_atividade") or "Atividade Pedagógica"
        obs = f" · Obs: {r.get('observacoes')}" if r.get("observacoes") else ""
        is_upd = bool(r.get("updated_by_name") and r.get("updated_by_name") != r.get("created_by_name"))
        operator = r.get("updated_by_name") if is_upd else (r.get("created_by_name") or "Secretaria Musical / Polo")

        records.append({
            "id": str(r.get("id")),
            "module": "musicalizacao",
            "module_label": MODULE_METADATA["musicalizacao"]["display_name"],
            "resource": "Aulas e Atividades",
            "action": "UPDATE" if is_upd else "CREATE",
            "created_by": operator,
            "created_at": r.get("created_at"),
            "location": f"{cidade} · {polo_name}" if cidade and polo_name else (cidade or polo_name or "Regional Itapevi"),
            "details": f"Aula '{nome_atv}' no polo {polo_name or 'não informado'} ({cidade}) em {data_fmt} · Participação: {tot} crianças ({m}M / {f}F) e {instr} instrutores{obs}.",
            "raw_data": r,
        })

    # 2. Cadastro de Crianças
    criancas = fetch_table("musicalizacao_criancas", {
        "select": "id,nome_crianca,polo_participacao,cidade,status,data_nascimento,created_at",
        "created_at": f"gte.{cutoff_iso}",
        "order": "created_at.desc",
        "limit": str(limit // 2),
    })
    for r in criancas:
        nome = r.get("nome_crianca") or "Criança sem nome"
        polo = clean_common(r.get("polo_participacao"))
        cidade = r.get("cidade") or ""
        st = r.get("status") or "Ativo"
        records.append({
            "id": str(r.get("id")),
            "module": "musicalizacao",
            "module_label": MODULE_METADATA["musicalizacao"]["display_name"],
            "resource": "Cadastro de Crianças",
            "action": "CREATE",
            "created_by": "Secretaria / Coordenação",
            "created_at": r.get("created_at"),
            "location": f"{cidade} · {polo}" if cidade and polo else (cidade or polo or "Regional Itapevi"),
            "details": f"Cadastro de aluno(a): {nome} no polo {polo or 'não informado'} ({cidade}) · Status cadastral: {st}.",
            "raw_data": r,
        })

    # 3. Presenças / Frequência
    presencas = fetch_table("musicalizacao_presenca", {
        "select": "id,aula_id,aluno_id,presente,status,observacoes,created_by_name,created_at",
        "created_at": f"gte.{cutoff_iso}",
        "order": "created_at.desc",
        "limit": str(limit // 2),
    })
    aula_ids = sorted({
        str(row.get("aula_id"))
        for row in presencas if row.get("aula_id")
    })
    aulas_by_id = {}
    if aula_ids:
        aulas_by_id = {
            str(row.get("id")): row
            for row in fetch_table("musicalizacao_aulas", {
                "select": "id,cidade,polo",
                "id": f"in.({','.join(aula_ids)})",
            })
            if row.get("id")
        }
    for r in presencas:
        st = r.get("status") or ("PRESENTE" if r.get("presente") else "FALTA")
        obs = f" ({r.get('observacoes')})" if r.get("observacoes") else ""
        operator = r.get("created_by_name") or "Instrutor / Chamada"
        aula = aulas_by_id.get(str(r.get("aula_id") or ""), {})
        audit_data = {**r, "cidade": aula.get("cidade"), "polo": aula.get("polo")}
        city = aula.get("cidade") or ""
        polo = aula.get("polo") or ""
        records.append({
            "id": str(r.get("id")),
            "module": "musicalizacao",
            "module_label": MODULE_METADATA["musicalizacao"]["display_name"],
            "resource": "Frequência e Chamadas",
            "action": "CREATE",
            "created_by": operator,
            "created_at": r.get("created_at"),
            "location": f"{city} · {polo}" if city and polo else (city or polo or "Polo de Musicalização"),
            "details": f"Registro de presença individual · Aluno ID: {r.get('aluno_id')} · Situação: {st}{obs}.",
            "raw_data": audit_data,
        })
    return records

def collect_cartas(cutoff_iso, limit=200):
    records = []
    cartas = fetch_table("cartas_emissoes", {
        "select": "id,nome,comum,municipio,tipo,modalidade,status,review_result,reviewed_name,reviewed_at,review_notes,created_by,created_at,updated_at,deleted_at,deleted_name",
        "created_at": f"gte.{cutoff_iso}",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    for r in cartas:
        nome = r.get("nome") or "Candidato(a)"
        comum = clean_common(r.get("comum"))
        muni = r.get("municipio") or ""
        tipo = (r.get("tipo") or "exame").title()
        mod = (r.get("modalidade") or "geral").title()
        status = str(r.get("status") or "").upper()
        deleted = bool(r.get("deleted_at"))

        if deleted:
            action = "DELETE"
            op = r.get("deleted_name") or "Secretaria Musical"
            details = f"Exclusão de carta de {tipo} ({mod}) do candidato {nome} da comum {comum} ({muni})."
        elif r.get("reviewed_at"):
            res = r.get("review_result") or "Confirmado"
            action = "APPROVE" if "APROV" in str(res).upper() else "UPDATE"
            op = r.get("reviewed_name") or "Secretaria Musical"
            notes = f" · Parecer: {r.get('review_notes')}" if r.get("review_notes") else ""
            details = f"Avaliação ministerial da carta de {tipo} ({mod}) para {nome} em {comum} ({muni}) · Resultado: {res}{notes}."
        else:
            action = "CREATE"
            op = r.get("created_by") or "Secretaria Musical"
            details = f"Emissão de carta de apresentação para {tipo} ({mod}): {nome} · Comum: {comum} ({muni}) · Status: {status}."

        records.append({
            "id": str(r.get("id")),
            "module": "cartas",
            "module_label": MODULE_METADATA["cartas"]["display_name"],
            "resource": "Cartas de Exames",
            "action": action,
            "created_by": op,
            "created_at": r.get("deleted_at") or r.get("reviewed_at") or r.get("updated_at") or r.get("created_at"),
            "location": f"{muni} · {comum}" if muni and comum else (muni or comum or "Regional Itapevi"),
            "details": details,
            "raw_data": r,
        })
    return records

def collect_visitas(cutoff_iso, limit=200):
    records = []
    visitas = fetch_table("visitas_lancamentos", {
        "select": "id,referencia_mes,referencia_ano,municipio,comum,total_visitas,gvi,gvm,gvmu,rf,re,status,observacoes,created_by,updated_by,created_at,updated_at",
        "created_at": f"gte.{cutoff_iso}",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    for r in visitas:
        comum = clean_common(r.get("comum"))
        muni = r.get("municipio") or ""
        mes = r.get("referencia_mes") or ""
        ano = r.get("referencia_ano") or ""
        tot = r.get("total_visitas") or 0
        gvi = r.get("gvi") or 0
        gvm = r.get("gvm") or 0
        rf = r.get("rf") or 0
        st = r.get("status") or "Lançado"
        is_upd = bool(r.get("updated_by"))
        op = r.get("updated_by") if is_upd else (r.get("created_by") or "Equipe de Visitas")
        obs = f" · Obs: {r.get('observacoes')}" if r.get("observacoes") else ""

        records.append({
            "id": str(r.get("id")),
            "module": "visitas",
            "module_label": MODULE_METADATA["visitas"]["display_name"],
            "resource": "Apontamento de Visitas",
            "action": "UPDATE" if is_upd else "CREATE",
            "created_by": op,
            "created_at": r.get("updated_at") if is_upd else r.get("created_at"),
            "location": f"{muni} · {comum}" if muni and comum else (muni or comum or "Regional Itapevi"),
            "details": f"Apontamento de visitas ref. {mes:02d}/{ano} na comum {comum} ({muni}) · Total: {tot} visitas (GVI: {gvi}, GVM: {gvm}, RF: {rf}) · Status: {st}{obs}.",
            "raw_data": r,
        })
    return records

def collect_darpe(cutoff_iso, limit=200):
    records = []
    papeletas = fetch_table("darpe_papeletas", {
        "select": "id,data,setor,local,municipio,comum,equipe,participacao,observacoes,created_by_name,created_at",
        "created_at": f"gte.{cutoff_iso}",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    for r in papeletas:
        local = r.get("local") or "Atendimento"
        comum = clean_common(r.get("comum"))
        muni = r.get("municipio") or ""
        data_p = format_date_br(r.get("data"))
        equipe = r.get("equipe") or []
        eq_count = len(equipe) if isinstance(equipe, list) else 0
        op = r.get("created_by_name") or "Responsável DARPE"
        obs = f" · Obs: {r.get('observacoes')}" if r.get("observacoes") else ""

        records.append({
            "id": str(r.get("id")),
            "module": "darpe",
            "module_label": MODULE_METADATA["darpe"]["display_name"],
            "resource": "Papeletas de Atendimento",
            "action": "CREATE",
            "created_by": op,
            "created_at": r.get("created_at"),
            "location": f"{muni} · {comum or local}" if muni else (comum or local or "Regional"),
            "details": f"Papeleta de atendimento DARPE em {local} ({muni}) em {data_p} · Equipe escalada com {eq_count} membros{obs}.",
            "raw_data": r,
        })
    return records

def collect_sam(cutoff_iso, limit=200):
    records = []
    events = fetch_table("sam_audit_events", {
        "select": "id,occurred_at,action_type,action_raw,target_type,target_name_snapshot,actor_name_snapshot,congregation_snapshot,device,platform,ip_address",
        "occurred_at": f"gte.{cutoff_iso}",
        "order": "occurred_at.desc",
        "limit": str(limit),
    })
    for r in events:
        act_raw = r.get("action_raw") or r.get("action_type") or "Ação SAM"
        tgt_type = r.get("target_type") or ""
        tgt_name = r.get("target_name_snapshot") or ""
        actor = r.get("actor_name_snapshot") or "Operador SAM"
        cong = canonical_common(r.get("congregation_snapshot") or "")
        dev = r.get("device") or r.get("platform") or "Web"

        act_code = "ACCESS" if "acess" in act_raw.lower() else ("UPDATE" if "alter" in act_raw.lower() or "edit" in act_raw.lower() else "CREATE")
        tgt_part = f" · Alvo: {tgt_type} '{tgt_name}'" if tgt_name else ""

        records.append({
            "id": str(r.get("id")),
            "module": "sam",
            "module_label": MODULE_METADATA["sam"]["display_name"],
            "resource": f"Histórico importado do SAM ({tgt_type or 'Geral'})",
            "action": act_code,
            "created_by": actor,
            "created_at": r.get("occurred_at"),
            "location": cong or "Regional Itapevi",
            "details": f"{act_raw}{tgt_part} na Congregação {cong or 'Regional Itapevi'} (Dispositivo: {dev}).",
            "source_label": "Histórico importado do SAM",
            "raw_data": r,
        })
    return records

def collect_gem(cutoff_iso, limit=200):
    records = []
    alunos = fetch_table("musica_acompanhamento_aluno", {
        "select": "id,nome_aluno,instrumento,nivel,status,comum_congregacao,municipio,lancado_por,observacoes,created_at,updated_at",
        "created_at": f"gte.{cutoff_iso}",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    authorized_users = gem_authorized_users(
        row.get("id") for row in alunos if not row.get("lancado_por")
    )
    for r in alunos:
        nome = r.get("nome_aluno") or "Aluno GEM"
        inst = r.get("instrumento") or "Instrumento"
        nivel = r.get("nivel") or "Iniciante"
        st = r.get("status") or "Ativo"
        comum = clean_common(r.get("comum_congregacao"))
        muni = r.get("municipio") or ""
        is_upd = bool(r.get("updated_at") and r.get("updated_at") != r.get("created_at"))
        authorized_by = authorized_users.get(str(r.get("id")))
        synchronized_catalog = not r.get("lancado_por") and not authorized_by
        op = (
            r.get("lancado_por")
            or authorized_by
            or "Sistema SAM — sincronização de catálogo"
        )
        audit_payload = {**r, "lancado_por": r.get("lancado_por")}
        if authorized_by:
            audit_payload.update({
                "responsavel_lancamento_sam": authorized_by,
                "origem_responsavel_lancamento": "autorizado_por do histórico importado do SAM",
            })
        obs = f" · Obs: {r.get('observacoes')}" if r.get("observacoes") else ""

        records.append({
            "id": str(r.get("id")),
            "module": "gem",
            "module_label": MODULE_METADATA["gem"]["display_name"],
            "resource": "Acompanhamento de Alunos",
            "action": "UPDATE" if is_upd else "CREATE",
            "created_by": op,
            "created_at": r.get("updated_at") if is_upd else r.get("created_at"),
            "location": f"{muni} · {comum}" if muni and comum else (muni or comum or "Regional Itapevi"),
            "details": f"Ficha pedagógica GEM: {nome} ({inst} · Nível: {nivel}) · Comum: {comum} ({muni}) · Status: {st}{obs}.",
            "detail_fields": {
                "kind": "gem",
                "title": "Ficha pedagógica",
                "student_name": nome,
                "instrument": inst,
                "level": nivel,
                "status": st,
            },
            "source_label": (
                "Lançamento autorizado no SAM"
                if authorized_by and not r.get("lancado_por")
                else (
                    "Sincronização do catálogo SAM"
                    if synchronized_catalog
                    else "Cadastro do GEM"
                )
            ),
            "raw_data": audit_payload,
        })
    return records

def collect_admin(cutoff_iso, limit=200):
    records = []
    logs = fetch_table("audit_logs", {
        "select": "id,user_id,action,module,details,ip_address,user_agent,created_at",
        "created_at": f"gte.{cutoff_iso}",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    user_ids = sorted({str(row.get("user_id")) for row in logs if row.get("user_id")})
    profiles = fetch_table("profiles", {
        "select": "user_id,full_name,username,comum,municipio,cidade",
        "user_id": f"in.({','.join(user_ids)})",
    }) if user_ids else []
    profiles_by_user_id = {
        str(profile.get("user_id")): profile
        for profile in profiles
        if profile.get("user_id")
    }

    for r in logs:
        raw_act = str(r.get("action") or "").upper()
        mod = str(r.get("module") or "ADMIN").upper()
        dtls = r.get("details") or {}
        actor = dtls.get("actor") or {}
        profile = profiles_by_user_id.get(str(r.get("user_id")), {})
        op = (
            profile.get("full_name")
            or profile.get("username")
            or actor.get("name")
            or dtls.get("actor_name")
            or r.get("user_id")
            or "Sistema"
        )
        ip = r.get("ip_address") or ""
        target = dtls.get("target") or {}
        target_name = target.get("name") or dtls.get("target_name") or dtls.get("email") or ""
        scope_str = actor.get("scope") or dtls.get("actor_sector") or ""
        profile_common = profile.get("comum") or profile.get("comum_congregacao")
        loc = (
            canonical_common(profile_common)
            or canonical_common(actor.get("comum") or target.get("comum"))
            or target.get("municipio")
            or scope_str
            or "Regional Itapevi"
        )

        if "APPROVED" in raw_act:
            action = "APPROVE"
            desc = f"Aprovou solicitação de acesso de {target_name or 'usuário'} (Perfil: {target.get('role') or 'Autorizado'}, Pasta: {target.get('sector') or scope_str})."
        elif "REJECTED" in raw_act:
            action = "REJECT"
            desc = f"Rejeitou solicitação de acesso de {target_name or 'usuário'}."
        elif "UPDATE" in raw_act:
            action = "UPDATE"
            desc = f"Atualizou cadastro e permissões de acesso do usuário {target_name or 'do sistema'}."
        elif "DELETE" in raw_act:
            action = "DELETE"
            desc = f"Exclusão de usuário ou registro de acesso {target_name or ''}."
        elif "LOGIN" in raw_act:
            action = "ACCESS"
            desc = f"Login efetuado com sucesso no portal administrativo (IP: {ip})."
        elif "LOGOUT" in raw_act or "INACTIVE" in raw_act:
            action = "ACCESS"
            desc = f"Sessão encerrada ({'inatividade' if 'INACTIVE' in raw_act else 'logout voluntário'})."
        elif "EXPORT" in raw_act:
            action = "EXPORT"
            desc = f"Exportação de dados no formato {str(dtls.get('format', 'arquivo')).upper()} contendo {dtls.get('row_count', 0)} registros."
        elif "VIEW" in raw_act:
            action = "ACCESS"
            page_title = dtls.get("page_title") or dtls.get("state_name") or "Página"
            desc = f"Visualizou página ou recurso '{page_title}'."
        else:
            action = "OPERATION"
            desc = f"Operação {raw_act} executada no módulo {mod} por {op}."

        records.append({
            "id": str(r.get("id")),
            "module": "admin",
            "module_label": MODULE_METADATA["admin"]["display_name"],
            "resource": f"Segurança & Acessos ({mod})",
            "action": action,
            "created_by": op,
            "created_at": r.get("created_at"),
            "location": loc,
            "details": desc,
            "source_label": "Auditoria administrativa do APP",
            "raw_data": r,
        })
    return records


COLLECTORS = {
    "musicalizacao": collect_musicalizacao,
    "cartas": collect_cartas,
    "visitas": collect_visitas,
    "darpe": collect_darpe,
    "sam": collect_sam,
    "gem": collect_gem,
    "admin": collect_admin,
}

GEM_HISTORY_SOURCES = (
    ("musica_acompanhamento_msa", "data_aula"),
    ("musica_acompanhamento_metodo", "data_inicio"),
    ("musica_acompanhamento_hinario", "data"),
    ("musica_acompanhamento_provas", "data_prova"),
    ("musica_acompanhamento_escala", "data"),
)


def gem_authorized_users(student_ids):
    """Obtém o responsável mais recente dos lançamentos SAM de cada aluno."""
    identifiers = sorted({str(student_id) for student_id in student_ids if student_id})
    if not identifiers:
        return {}

    authorized_by_student = {}
    for table, date_field in GEM_HISTORY_SOURCES:
        rows = fetch_table(table, {
            "select": f"aluno_id,autorizado_por,{date_field}",
            "aluno_id": f"in.({','.join(identifiers)})",
            "autorizado_por": "not.is.null",
            "order": f"{date_field}.desc",
        })
        for row in rows:
            student_id = str(row.get("aluno_id") or "")
            authorized_by = str(row.get("autorizado_por") or "").strip()
            activity_date = str(row.get(date_field) or "")
            current = authorized_by_student.get(student_id)
            if authorized_by and (
                current is None or activity_date > current["activity_date"]
            ):
                authorized_by_student[student_id] = {
                    "name": authorized_by,
                    "activity_date": activity_date,
                }
    return {
        student_id: data["name"]
        for student_id, data in authorized_by_student.items()
    }


# ==============================================================================
# API Principal de Auditoria Genérica
# ==============================================================================

def can_access_audit_module(request, module):
    """Aplica a permissão de pasta também às consultas consolidadas."""
    if module not in COLLECTORS:
        return False
    if is_global(request.session.get("user_profile") or {}):
        return True
    return module in {"musicalizacao", "visitas", "darpe", "gem"} and can_access_module(request, module)


def audit_record_in_scope(scope, record):
    if scope.get("level") in {"global", "regional"}:
        return True

    raw_data = record.get("raw_data")
    if not isinstance(raw_data, dict):
        return False

    common = next((
        str(raw_data.get(field) or "").strip()
        for field in ("comum", "comum_congregacao", "polo", "polo_participacao", "congregation_snapshot")
        if str(raw_data.get(field) or "").strip()
    ), "")
    municipality = str(raw_data.get("municipio") or raw_data.get("cidade") or "").strip()
    if common:
        common = canonical_common(common)

    return can_access(scope, {"comum": common, "municipio": municipality})


def api_audit_generic(request, module):
    """API genérica e centralizada de auditoria consolidada para todos os módulos.

    Aceita:
    - module: módulo específico ('musicalizacao', 'cartas', etc.) ou 'all'/'todos'/''
    - period: dias de histórico (7, 30, 90, 365, 0/all)
    - date_from, date_to: intervalo explícito AAAA-MM-DD
    - resource: recurso específico
    - action: código de ação ('CREATE', 'UPDATE', 'DELETE', etc.)
    - operator: termo de busca para operador
    - search: busca livre nos detalhes, operador ou localização
    """
    if request.method.upper() != "GET":
        return JsonResponse({"error": "Apenas GET permitido."}, status=405)

    scope = user_scope(request)

    # Validação do módulo solicitado
    target_module = str(module or "").lower().strip()
    if target_module in {"", "all", "todos", "global"}:
        modules_to_query = [
            module_name
            for module_name in COLLECTORS
            if can_access_audit_module(request, module_name)
        ]
        if not modules_to_query:
            return JsonResponse({"error": "Acesso não autorizado à auditoria."}, status=403)
    elif target_module in COLLECTORS:
        if not can_access_audit_module(request, target_module):
            return JsonResponse({"error": "Acesso não autorizado a este módulo."}, status=403)
        modules_to_query = [target_module]
    else:
        return JsonResponse({"error": f"Módulo '{target_module}' não reconhecido."}, status=404)

    # Parâmetros de filtro temporal
    period_days = request.GET.get("period")
    date_from = request.GET.get("date_from") or request.GET.get("data_inicio") or ""
    date_to = request.GET.get("date_to") or request.GET.get("data_fim") or ""

    now_utc = datetime.now(timezone.utc)
    if date_from:
        try:
            cutoff_dt = datetime.strptime(date_from[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            cutoff_dt = now_utc - timedelta(days=30)
    elif period_days and str(period_days).isdigit() and int(period_days) > 0:
        cutoff_dt = now_utc - timedelta(days=int(period_days))
    else:
        # Default: 30 dias
        cutoff_dt = now_utc - timedelta(days=30)

    cutoff_iso = cutoff_dt.isoformat()
    limit_per_module = 300 if len(modules_to_query) == 1 else 150

    # Execução concorrente dos coletores
    all_records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(modules_to_query), 6)) as executor:
        future_map = {executor.submit(COLLECTORS[m], cutoff_iso, limit_per_module): m for m in modules_to_query}
        for future in concurrent.futures.as_completed(future_map):
            mod_name = future_map[future]
            try:
                res = future.result()
                all_records.extend(res)
            except Exception as e:
                logger.exception("Erro ao coletar auditoria do módulo %s: %s", mod_name, e)

    # Filtros em memória
    action_filter = str(request.GET.get("action") or "").upper().strip()
    resource_filter = str(request.GET.get("resource") or "").lower().strip()
    operator_filter = str(request.GET.get("operator") or "").lower().strip()
    search_filter = str(request.GET.get("search") or "").lower().strip()
    location_filter = str(request.GET.get("location") or request.GET.get("municipio") or "").lower().strip()

    filtered_records = []
    unique_operators = set()
    action_counts = {"creates": 0, "updates": 0, "deletes": 0, "accesses": 0, "others": 0}
    module_counts = {m: 0 for m in MODULE_METADATA.keys()}
    daily_timeline = {}

    for rec in all_records:
        if not audit_record_in_scope(scope, rec):
            continue
        rec_dt = parse_iso(rec.get("created_at"))
        if not rec_dt:
            continue
        rec["created_by"] = canonical_operator_name(rec.get("created_by"))

        # Filtro de data máxima se especificado
        if date_to:
            try:
                max_dt = datetime.strptime(date_to[:10], "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
                if rec_dt > max_dt:
                    continue
            except (TypeError, ValueError):
                logger.warning("Filtro date_to inválido: %r", date_to)

        # Filtro de ação
        rec_action = str(rec.get("action") or "").upper()
        if action_filter and action_filter != "ALL" and action_filter != "TODAS":
            if action_filter not in rec_action:
                continue

        # Filtro de recurso
        rec_resource = str(rec.get("resource") or "").lower()
        if resource_filter and resource_filter not in rec_resource:
            continue

        # Filtro de operador
        rec_op = str(rec.get("created_by") or "")
        if operator_filter and operator_filter not in rec_op.lower():
            continue

        # Filtro de localização / município
        rec_loc = str(rec.get("location") or "")
        if location_filter and location_filter not in rec_loc.lower():
            continue

        # Filtro de busca livre
        if search_filter:
            haystack = f"{rec.get('details', '')} {rec_op} {rec_loc} {rec.get('module_label', '')} {rec.get('resource', '')}".lower()
            if search_filter not in haystack:
                continue

        # Enriquecimento com formatação de apresentação
        rec["created_at_display"] = format_datetime_br(rec.get("created_at"))
        rec["time_ago"] = compute_relative_time(rec.get("created_at"), now_utc)
        badge_meta = get_action_badge_meta(rec_action)
        rec["action_label"] = badge_meta["label"]
        rec["action_class"] = badge_meta["class"]
        rec["action_color"] = badge_meta["color"]
        rec["action_bg"] = badge_meta["bg"]

        mod_meta = MODULE_METADATA.get(rec.get("module"), {})
        rec["module_icon"] = mod_meta.get("icon", "fa-clipboard-check")
        rec["module_badge_class"] = mod_meta.get("badge_class", "badge-secondary")
        rec["module_badge_bg"] = mod_meta.get("badge_bg", "#f1f5f9")
        rec["module_badge_color"] = mod_meta.get("badge_color", "#475569")

        filtered_records.append(rec)

        # Agregações analíticas
        if rec_op and rec_op != "Sistema":
            unique_operators.add(rec_op)

        if rec_action == "CREATE":
            action_counts["creates"] += 1
        elif rec_action == "UPDATE":
            action_counts["updates"] += 1
        elif rec_action in {"DELETE", "REJECT"}:
            action_counts["deletes"] += 1
        elif rec_action == "ACCESS":
            action_counts["accesses"] += 1
        else:
            action_counts["others"] += 1

        mod_key = rec.get("module")
        if mod_key in module_counts:
            module_counts[mod_key] += 1

        # Ponto na linha do tempo diária
        day_str = rec_dt.strftime("%Y-%m-%d")
        daily_timeline[day_str] = daily_timeline.get(day_str, 0) + 1

    # Ordenação decrescente cronológica estrita
    filtered_records.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)

    # Série temporal formatada para ApexCharts
    sorted_days = sorted(daily_timeline.keys())
    if sorted_days:
        start_d = datetime.strptime(sorted_days[0], "%Y-%m-%d").date()
        end_d = datetime.strptime(sorted_days[-1], "%Y-%m-%d").date()
        delta = (end_d - start_d).days
        timeline_series = []
        for i in range(min(delta + 1, 90)):
            curr_d = start_d + timedelta(days=i)
            curr_str = curr_d.strftime("%Y-%m-%d")
            timeline_series.append({
                "date": curr_str,
                "label": curr_d.strftime("%d/%m"),
                "count": daily_timeline.get(curr_str, 0)
            })
    else:
        timeline_series = []

    # Geração da Leitura de Gestão Executiva
    total = len(filtered_records)
    active_ops = len(unique_operators)
    creates = action_counts["creates"]
    updates = action_counts["updates"]
    deletes = action_counts["deletes"]

    top_mod_name = "Nenhum"
    if any(module_counts.values()):
        top_mod_key = max(module_counts, key=module_counts.get)
        top_mod_name = MODULE_METADATA.get(top_mod_key, {}).get("display_name", top_mod_key)

    last_op_text = "Sem movimentações recentes"
    if filtered_records:
        latest = filtered_records[0]
        last_op_text = f"última atividade registrada {latest.get('time_ago', '')} por {latest.get('created_by', 'Sistema')}"

    executive_note = (
        f"Leitura de gestão: {total} operação(ões) auditada(s) no período com {active_ops} operador(es) ativo(s); "
        f"{creates} inclusão(ões), {updates} atualização(ões) e {deletes} exclusão(ões). "
        f"Módulo com maior atividade: {top_mod_name}. {last_op_text}."
    )

    scope_display = "Regional Itapevi"
    if isinstance(scope, dict):
        scope_level = scope.get("level") or scope.get("nivel") or "regional"
        scope_muni = scope.get("municipio") or ""
        scope_display = f"{scope_level.title()}{(' · ' + scope_muni) if scope_muni else ' - Regional Itapevi'}"

    return JsonResponse({
        "records": filtered_records,
        "total_events": total,
        "active_operators": active_ops,
        "action_counts": action_counts,
        "module_counts": module_counts,
        "timeline_series": timeline_series,
        "executive_note": executive_note,
        "scope": scope_display,
        "scope_raw": scope,
        "timestamp": now_utc.astimezone(SAO_PAULO_TIME_ZONE).strftime("%d/%m/%Y %H:%M"),
    }, status=200)
