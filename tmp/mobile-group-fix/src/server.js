const http = require("http");
const fs = require("fs");
const path = require("path");
const { URL } = require("url");

const rootDir = process.cwd();
const publicDir = path.join(rootDir, "public");
const envFile = path.join(rootDir, ".env");

if (fs.existsSync(envFile)) {
  for (const line of fs.readFileSync(envFile, "utf8").split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (!match || match[2].trim().startsWith("#")) continue;
    const value = match[2].trim().replace(/^(['"])(.*)\1$/, "$2");
    if (process.env[match[1]] === undefined) process.env[match[1]] = value;
  }
}

const PORT = Number(process.env.PORT || 3000);
const SUPABASE_URL = String(process.env.SUPABASE_URL || "").replace(/\/$/, "");
const SUPABASE_ANON_KEY = process.env.SUPABASE_ANON_KEY || "";
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "";
const PASSWORD_RECOVERY_REDIRECT_URL = String(process.env.PASSWORD_RECOVERY_REDIRECT_URL || "").trim();
const TABLE_PROFILES = process.env.SUPABASE_TABLE_PROFILES || "profiles";
const TABLE_MEMBERS = process.env.SUPABASE_TABLE_VISITAS_IRMANDADE || "visitas_irmandade";
const TABLE_AGENDA = process.env.SUPABASE_TABLE_VISITAS_AGENDA || "visitas_agenda";
const RECENT_VISIT_INTERVAL_DAYS = 35;

const mimeTypes = {
  ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8", ".png": "image/png",
  ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".ico": "image/x-icon"
};

function sendJson(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
  res.end(JSON.stringify(body));
}

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 1_000_000) throw Object.assign(new Error("Payload muito grande."), { status: 413 });
    chunks.push(chunk);
  }
  try { return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {}; }
  catch { throw Object.assign(new Error("JSON inválido."), { status: 400 }); }
}

function requiredConfig() {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY || !SERVICE_KEY) {
    throw Object.assign(new Error("Integração com o sistema de visitas não configurada."), { status: 503 });
  }
}

function serviceHeaders(prefer = "") {
  const headers = { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}`, "Content-Type": "application/json" };
  if (prefer) headers.Prefer = prefer;
  return headers;
}

async function supabase(table, { method = "GET", query = {}, body, prefer = "" } = {}) {
  requiredConfig();
  // A localidade da visita pertence ao cadastro da irmandade e é obtida por
  // irmandade_id. A tabela visitas_agenda não possui essas colunas.
  if (table === TABLE_AGENDA && body && !Array.isArray(body)) {
    body = { ...body };
    delete body.comum;
    delete body.municipio;
    delete body.cidade;
  }
  const url = new URL(`${SUPABASE_URL}/rest/v1/${table}`);
  Object.entries(query).forEach(([key, value]) => {
    if (Array.isArray(value)) value.forEach(item => url.searchParams.append(key, item));
    else if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  });
  const response = await fetch(url, {
    method, headers: serviceHeaders(prefer), body: body === undefined ? undefined : JSON.stringify(body)
  });
  const text = await response.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { payload = text; }
  if (!response.ok) {
    const message = payload?.message || payload?.error || "Falha ao acessar o banco de visitas.";
    throw Object.assign(new Error(message), { status: response.status, details: payload });
  }
  return payload;
}

function bearer(req) {
  const value = String(req.headers.authorization || "");
  return value.startsWith("Bearer ") ? value.slice(7).trim() : "";
}

async function authenticatedUser(req) {
  requiredConfig();
  const token = bearer(req);
  if (!token) throw Object.assign(new Error("Faça login para continuar."), { status: 401 });
  const response = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
    headers: { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${token}` }
  });
  if (!response.ok) throw Object.assign(new Error("Sua sessão expirou. Faça login novamente."), { status: 401 });
  return response.json();
}

function normalize(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR").replace(/\s+/g, " ").trim();
}

function normalizeAddress(value) {
  return normalize(String(value || "").replace(/^\[[^\]]+\]\s*/, ""))
    .replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
}

function truthy(value) {
  return [true, "true", "1", "on"].includes(value);
}

async function recentFamilyVisit(member, members, scheduledStart) {
  const memberId = String(member?.id || "").trim();
  const address = normalizeAddress(member?.endereco);
  const householdIds = Array.from(new Set((members || [])
    .filter(item => String(item.id || "").trim() === memberId
      || (address && normalizeAddress(item.endereco) === address))
    .map(item => String(item.id || "").trim()).filter(Boolean)));
  if (memberId && !householdIds.includes(memberId)) householdIds.push(memberId);

  const select = "id,irmandade_id,titulo,data_inicio,equipe_responsavel,status,endereco_visitado";
  const commonQuery = {
    select,
    status: "eq.Realizada",
    data_inicio: `lt.${scheduledStart.toISOString()}`,
    order: "data_inicio.desc",
    limit: "100"
  };
  const requests = [];
  if (householdIds.length) {
    requests.push(supabase(TABLE_AGENDA, {
      query: { ...commonQuery, irmandade_id: `in.(${householdIds.join(",")})` }
    }).catch(() => []));
  }
  if (String(member?.endereco || "").trim()) {
    requests.push(supabase(TABLE_AGENDA, {
      query: { ...commonQuery, endereco_visitado: `eq.${String(member.endereco).trim()}` }
    }).catch(() => []));
  }
  if (!requests.length) return null;

  const rows = (await Promise.all(requests)).flat().filter((visit, index, all) =>
    visit?.data_inicio && all.findIndex(item => String(item.id) === String(visit.id)) === index
  );
  const related = rows.filter(visit => householdIds.includes(String(visit.irmandade_id || ""))
    || (address && normalizeAddress(visit.endereco_visitado) === address));
  related.sort((left, right) => new Date(right.data_inicio) - new Date(left.data_inicio));
  const latest = related[0];
  if (!latest) return null;

  const lastVisitDate = new Date(latest.data_inicio);
  const intervalDays = Math.max(0, Math.floor((scheduledStart - lastVisitDate) / 86_400_000));
  if (intervalDays >= RECENT_VISIT_INTERVAL_DAYS) return null;
  const elapsedDays = Math.max(0, Math.floor((new Date() - lastVisitDate) / 86_400_000));
  return {
    dias_desde_visita: elapsedDays,
    intervalo_entre_visitas: intervalDays,
    equipe: String(latest.equipe_responsavel || "Equipe não informada").trim(),
    data_visita: latest.data_inicio,
    intervalo_recomendado: RECENT_VISIT_INTERVAL_DAYS
  };
}

function findSameDayFamilyVisit(visits, member, householdIds, targetDate) {
  const memberId = String(member?.id || "").trim();
  const address = normalizeAddress(member?.endereco);
  return (visits || []).find(visit => {
    if (!visit?.data_inicio || visit.status === "Cancelada") return false;
    const visitDate = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" })
      .format(new Date(visit.data_inicio));
    const sameFamily = householdIds.includes(String(visit.irmandade_id || ""))
      || (memberId && String(visit.irmandade_id || "") === memberId)
      || (address && normalizeAddress(visit.endereco_visitado) === address);
    return visitDate === targetDate && sameFamily;
  }) || null;
}

async function requireNoSameDayFamilyVisit(member, context, targetDate) {
  const memberId = String(member?.id || "").trim();
  const address = normalizeAddress(member?.endereco);
  const householdIds = Array.from(new Set((context.members || [])
    .filter(item => String(item.id || "").trim() === memberId
      || (address && normalizeAddress(item.endereco) === address))
    .map(item => String(item.id || "").trim()).filter(Boolean)));
  if (memberId && !householdIds.includes(memberId)) householdIds.push(memberId);

  const dayStart = new Date(`${targetDate}T00:00:00-03:00`);
  const dayEnd = new Date(dayStart.getTime() + 24 * 60 * 60 * 1000);
  const query = {
    select: "id,irmandade_id,titulo,data_inicio,equipe_responsavel,status,endereco_visitado",
    and: `(data_inicio.gte.${dayStart.toISOString()},data_inicio.lt.${dayEnd.toISOString()})`,
    order: "data_inicio.asc",
    limit: "1000"
  };
  const requests = [];
  if (householdIds.length) {
    requests.push(supabase(TABLE_AGENDA, {
      query: { ...query, irmandade_id: `in.(${householdIds.join(",")})` }
    }));
  }
  if (String(member?.endereco || "").trim()) {
    requests.push(supabase(TABLE_AGENDA, {
      query: { ...query, endereco_visitado: `eq.${String(member.endereco).trim()}` }
    }));
  }
  const visits = (await Promise.all(requests)).flat().filter((visit, index, all) =>
    visit?.data_inicio && all.findIndex(item => String(item.id) === String(visit.id)) === index
  );
  const existingVisit = findSameDayFamilyVisit(visits, member, householdIds, targetDate);
  if (!existingVisit) return;

  throw Object.assign(
    new Error("Já existe uma visita agendada para esta família nesta data. Revise o agendamento existente."),
    {
      status: 409,
      code: "DUPLICATE_FAMILY_VISIT_SAME_DAY",
      existingVisit: {
        equipe: String(existingVisit.equipe_responsavel || "Equipe não informada").trim(),
        data_visita: existingVisit.data_inicio,
        titulo: String(existingVisit.titulo || member.nome || "Família").trim()
      }
    }
  );
}

async function requireRecentVisitConfirmation(body, member, context, scheduledStart) {
  if (truthy(body.confirmar_visita_recente)) return;
  const recentVisit = await recentFamilyVisit(member, context.members, scheduledStart);
  if (!recentVisit) return;
  const when = recentVisit.dias_desde_visita === 0
    ? "hoje"
    : `há ${recentVisit.dias_desde_visita} ${recentVisit.dias_desde_visita === 1 ? "dia" : "dias"}`;
  throw Object.assign(
    new Error(`Esta família já foi visitada ${when} pela ${recentVisit.equipe}. Confirme para agendar uma nova visita.`),
    { status: 409, code: "RECENT_FAMILY_VISIT", recentVisit }
  );
}

function uniqueMemberByNameParts(members, profileName) {
  const searchedParts = normalize(profileName).split(" ").filter(part => part.length > 1);
  if (searchedParts.length < 2) return null;
  const matches = members.filter(item => {
    const memberParts = new Set(normalize(item.nome).split(" ").filter(Boolean));
    return searchedParts.every(part => memberParts.has(part));
  });
  return matches.length === 1 ? matches[0] : null;
}

async function mobileContext(req, url = null) {
  const user = await authenticatedUser(req);
  const profiles = await supabase(TABLE_PROFILES, {
    query: { select: "*", user_id: `eq.${user.id}`, limit: "1" }
  });
  const profile = Array.isArray(profiles) ? profiles[0] : null;
  if (!profile || profile.status !== "approved") {
    throw Object.assign(new Error("Seu acesso ainda não está aprovado ou foi desativado."), { status: 403 });
  }

  const roleId = Number(profile.role_id || 99);
  const roleName = String(profile.role || profile.nivel || "").trim().toUpperCase();
  const canViewRestrictedNotes = roleId >= 1 && roleId <= 3;
  const explicitLevel = String(profile.access_level || profile.nivel_acesso || profile.escopo || "").trim().toLowerCase();
  const level = ["local", "municipal", "regional", "global"].includes(explicitLevel)
    ? explicitLevel
    : (roleId === 1 ? "global" : roleId === 2 ? "regional" : roleId === 3 ? "municipal" : "local");
  const canHighlightExcessDuration = level === "global" || ["MASTER", "GLOBAL"].includes(roleName);

  const isGlobal = level === "global" || level === "regional" || level === "municipal";

  const requestedComum = url?.searchParams?.get("comum");
  const requestedMunicipio = url?.searchParams?.get("municipio") || url?.searchParams?.get("cidade");

  const defaultComum = String(profile.comum || user.user_metadata?.comum || "").trim();
  const defaultMunicipio = String(profile.municipio || profile.cidade || "").trim();

  let comum = defaultComum;
  let municipio = defaultMunicipio;

  if (isGlobal) {
    comum = requestedComum !== null && requestedComum !== undefined ? requestedComum.trim() : defaultComum;
    municipio = requestedMunicipio !== null && requestedMunicipio !== undefined ? requestedMunicipio.trim() : defaultMunicipio;
  } else {
    comum = defaultComum;
    municipio = defaultMunicipio;
  }

  let memberQuery = { select: "*", limit: "1000" };
  if (comum) {
    memberQuery.or = `(comum.eq.${comum},comum.ilike.%${comum}%)`;
  } else if (municipio) {
    memberQuery.or = `(cidade.eq.${municipio},cidade.ilike.%${municipio}%)`;
  }

  const members = (comum || municipio || isGlobal) ? await supabase(TABLE_MEMBERS, {
    query: memberQuery
  }).catch(() => []) : [];

  const profileName = normalize(profile.full_name || profile.username || user.user_metadata?.full_name);
  const explicitId = String(profile.irmandade_id || profile.membro_id || "");
  let member = null;
  if (explicitId) {
    const linked = await supabase(TABLE_MEMBERS, { query: { select: "*", id: `eq.${explicitId}`, limit: "1" } });
    member = linked[0] || null;
  } else {
    if (!member && profileName) {
      // Resolve identity independently of the selected destination comum.
      const candidates = [];
      for (let offset = 0; ; offset += 500) {
        const page = await supabase(TABLE_MEMBERS, { query: { select: "*", order: "id.asc", limit: "500", offset: String(offset) } });
        candidates.push(...page);
        if (page.length < 500) break;
      }
      member = identifyMember(candidates, profileName, defaultComum);
    }
  }
  const hasRegisteredMember = Boolean(member);
  if (member && !isGlobal) {
    comum = String(member.comum || defaultComum).trim();
    municipio = String(member.cidade || defaultMunicipio).trim();
  }

  if (!member) {
    member = {
      id: explicitId || `mock-${Date.now()}`,
      nome: profileName || 'Usuário de Teste',
      equipe_visita: profile.equipe_visita || '',
      grupo_regional_nome: profile.grupo_regional_nome || '',
      cidade: municipio || profile.municipio || profile.cidade || ''
    };
    members.push(member);
  }

  // Both registered assignments participate automatically in the personal route.
  const teams = teamAssignments(hasRegisteredMember, member);
  const assignment = resolveTeamAssignment(hasRegisteredMember, member);
  const personalTeams = teams.map(team => ({ ...team, comum: member.comum || defaultComum, municipio: member.cidade || defaultMunicipio }));
  const { equipe, equipeId, teamType } = assignment;
  return {
    user, profile, member, members,
    equipe, equipeId, comum, teamType, teams: personalTeams,
    municipio: municipio || String(profile.municipio || profile.cidade || member.cidade || "").trim(),
    level, isGlobal, roleId, canViewRestrictedNotes, canHighlightExcessDuration
  };
}

function validDate(value) {
  const date = String(value || "");
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit", day: "2-digit"
  }).format(new Date());
}

function normalizeTeam(name) {
  return String(name || "").trim().toLowerCase().replace(/equipe\s*0*(\d+)/i, "equipe $1");
}

function identifyMember(candidates, name, comum) {
  const exact = candidates.filter(item => normalize(item.nome) === normalize(name));
  if (exact.length === 1) return exact[0];
  if (exact.length > 1) return null;
  const parts = uniqueMemberByNameParts(candidates, name);
  if (parts) return parts;
  return uniqueMemberByNameParts(candidates.filter(item => normalize(item.comum) === normalize(comum)), name);
}

function visitMatchesSelectedScope(context, visit) {
  const common = normalize(context.comum);
  const city = normalize(context.municipio);
  const visitCommon = normalize(visit.comum);
  const visitCity = normalize(visit.municipio || visit.cidade);
  if (context.level === "municipal") {
    const permittedCity = normalize(context.profile?.municipio || context.profile?.cidade);
    if (!permittedCity || visitCity !== permittedCity) return false;
  }
  if (common && !["todas", "todos"].includes(common)) return visitCommon === common;
  if (city && !["todos", "todos os municipios"].includes(city)) return visitCity === city;
  return Boolean(context.isGlobal);
}

function personalVisitAccess(context, visit, member) {
  const teams = context.teams || [context];
  return teams.some(team => {
    if (!visitBelongsToContextTeam(team, visit)) return false;
    const common = normalize(visit.comum || member?.comum);
    const city = normalize(visit.municipio || visit.cidade || member?.cidade);
    if (team.teamType === "REGIONAL") return !city || !team.municipio || city === normalize(team.municipio);
    return !common || !team.comum || common === normalize(team.comum);
  });
}

function teamAssignments(registered, member = {}) {
  if (!registered) return [];
  return [
    { key: "local", equipe: String(member.equipe_visita || "").trim(), equipeId: member.equipe_id || null, teamType: "LOCAL" },
    { key: "regional", equipe: String(member.grupo_regional_nome || "").trim(), equipeId: member.grupo_regional_id || null, teamType: "REGIONAL" }
  ].filter(team => team.equipe || team.equipeId).map(team => ({ ...team, equipe: team.equipe || team.equipeId }));
}

function resolveTeamAssignment(hasRegisteredMember, member = {}) {
  if (!hasRegisteredMember) {
    return { equipe: "", equipeId: null, teamType: "LOCAL" };
  }
  const source = member;
  const localTeam = String(source.equipe_visita || "").trim();
  const regionalTeam = String(source.grupo_regional_nome || "").trim();
  const equipe = localTeam || regionalTeam;
  return {
    equipe,
    equipeId: (localTeam ? source.equipe_id : regionalTeam ? source.grupo_regional_id : null) || null,
    teamType: localTeam ? "LOCAL" : regionalTeam ? "REGIONAL" : "LOCAL"
  };
}

function visitBelongsToContextTeam(context, visit) {
  if (!context?.equipe || !visit) return false;
  if (visit.equipe_tipo && context.teamType && visit.equipe_tipo !== context.teamType) return false;
  if (context.equipeId && visit.equipe_id) {
    return String(context.equipeId) === String(visit.equipe_id);
  }
  const contextTeam = normalizeTeam(context.equipe);
  const visitTeam = normalizeTeam(visit.equipe_responsavel);
  return Boolean(contextTeam && visitTeam && contextTeam === visitTeam);
}


const PERIOD_MARKER = /\s*\[\[periodo_planejado:(manha|tarde|noite)\]\]\s*/gi;
const ACTUAL_TIME_MARKER = /\s*\[\[horario_realizado:(\d{2}:\d{2})\]\]\s*/gi;
const START_TIME_MARKER = /\s*\[\[horario_inicio:(\d{2}:\d{2})\]\]\s*/gi;
const END_TIME_MARKER = /\s*\[\[horario_fim:(\d{2}:\d{2})\]\]\s*/gi;

function plannedPeriodFromNotes(notes) {
  const match = String(notes || "").match(/\[\[periodo_planejado:(manha|tarde|noite)\]\]/i);
  return match ? match[1].toLowerCase() : "";
}

function startTimeFromNotes(notes) {
  const text = String(notes || "");
  const match = text.match(/\[\[horario_inicio:(\d{2}:\d{2})\]\]/i)
    || text.match(/\[\[horario_realizado:(\d{2}:\d{2})\]\]/i);
  return match ? match[1] : "";
}

function endTimeFromNotes(notes) {
  const match = String(notes || "").match(/\[\[horario_fim:(\d{2}:\d{2})\]\]/i);
  return match ? match[1] : "";
}

function visibleVisitNotes(notes) {
  return String(notes || "")
    .replace(PERIOD_MARKER, " ")
    .replace(ACTUAL_TIME_MARKER, " ")
    .replace(START_TIME_MARKER, " ")
    .replace(END_TIME_MARKER, " ")
    .replace(/\s{2,}/g, " ").trim();
}

function notesWithPlannedPeriod(notes, period) {
  const visible = visibleVisitNotes(notes);
  const startTime = startTimeFromNotes(notes);
  const endTime = endTimeFromNotes(notes);
  const markers = [
    `[[periodo_planejado:${period}]]`,
    startTime ? `[[horario_inicio:${startTime}]]` : "",
    endTime ? `[[horario_fim:${endTime}]]` : ""
  ].filter(Boolean);
  return [visible, ...markers].filter(Boolean).join(" ");
}

function notesWithVisitMetadata(notes, period, startTime, endTime) {
  return [
    visibleVisitNotes(notes),
    period ? `[[periodo_planejado:${period}]]` : "",
    startTime ? `[[horario_inicio:${startTime}]]` : "",
    endTime ? `[[horario_fim:${endTime}]]` : ""
  ].filter(Boolean).join(" ");
}

function getMemberPhone(m) {
  if (!m) return "";
  const phone = m.celular || m.telefone || m.whatsapp || m.celular_contato || m.telefone_contato || m.contato || m.fone || m.phone || "";
  return String(phone || "").trim();
}

function canAccess(context, visit, member) {
  const level = context.level || "local";
  if (level === "global" || level === "regional") return true;

  const visitCity = normalize(visit.municipio || visit.cidade || member?.cidade || member?.municipio);
  const userCity = normalize(context.municipio);

  if (level === "municipal") {
    return !userCity || !visitCity || visitCity === userCity;
  }

  // Um grupo regional é municipal e pode reunir integrantes de várias comuns.
  // A equipe local continua estritamente limitada à comum do usuário.
  const userComum = normalize(context.comum);
  const visitComum = normalize(visit.comum);
  const memberComum = normalize(member?.comum);
  const targetComum = visitComum || memberComum;

  if (context.teamType !== "REGIONAL" && userComum && targetComum && targetComum !== userComum) {
    return false;
  }

  if (context.teamType !== "REGIONAL" && userComum && !targetComum && member) {
    const belongsToComum = context.members?.some(m => String(m.id) === String(member.id));
    if (!belongsToComum) return false;
  }

  const userTeamNorm = normalizeTeam(context.equipe);
  // A equipe pertence à visita, nunca ao cadastro de quem será visitado.
  const visitTeamNorm = normalizeTeam(visit.equipe_responsavel);

  if (userTeamNorm && visitTeamNorm && visitTeamNorm !== userTeamNorm) {
    return false;
  }

  return true;
}

async function teamVisits(context, date) {
  // A agenda pertence ao participante logado e à equipe dele. Sem vínculo de
  // equipe no cadastro da irmandade, nenhuma visita pode ser carregada.
  if (!context.isGlobal && !context.teams?.length && !context.equipe) return [];
  const next = new Date(`${date}T12:00:00-03:00`);
  next.setDate(next.getDate() + 1);
  const end = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(next);
  
  const query = {
    select: "*",
    and: `(data_inicio.gte.${date}T00:00:00-03:00,data_inicio.lt.${end}T00:00:00-03:00)`,
    order: "data_inicio.asc", limit: "500"
  };

  // Personal routes combine all registered assignments regardless of access level.
  // Filter in memory so canonical IDs and legacy names are both supported.
  // A non-null conflicting ID never falls back to a matching name.
  const dayRows = [];
  for (let offset = 0; ; offset += 500) {
    const page = await supabase(TABLE_AGENDA, { query: { ...query, order: "data_inicio.asc,id.asc", offset: String(offset) } });
    dayRows.push(...page);
    if (page.length < 500) break;
  }
  const rows = dayRows.filter(visit => context.isGlobal || (context.teams || [context]).some(team => visitBelongsToContextTeam(team, visit)));

  const irmandadeIds = Array.from(new Set(rows.map(r => String(r.irmandade_id || "")).filter(Boolean)));
  let visitMembers = context.members ? [...context.members] : [];

  if (irmandadeIds.length > 0) {
    try {
      const fetched = await supabase(TABLE_MEMBERS, {
        query: { select: "*", id: `in.(${irmandadeIds.join(",")})` }
      });
      if (Array.isArray(fetched)) {
        const existingIds = new Set(visitMembers.map(m => String(m.id)));
        fetched.forEach(m => {
          if (!existingIds.has(String(m.id))) visitMembers.push(m);
        });
      }
    } catch (e) {
      console.error("Falha ao buscar detalhes dos membros por ID:", e);
    }
  }

  for (const visit of rows) {
    const cleanName = String(visit.titulo || "").replace(/^visita\s*-\s*/i, "").replace(/^visita\s+/i, "").trim();
    if (!cleanName) continue;

    const foundById = visitMembers.find(m => String(m.id) === String(visit.irmandade_id || ""));
    const foundByName = visitMembers.find(m => normalize(m.nome) === normalize(cleanName));

    if (!foundById && !foundByName) {
      try {
        const fetchedExact = await supabase(TABLE_MEMBERS, {
          query: { select: "*", nome: `eq.${cleanName}` }
        });
        if (Array.isArray(fetchedExact) && fetchedExact.length > 0) {
          fetchedExact.forEach(m => visitMembers.push(m));
        } else {
          const fetchedIlike = await supabase(TABLE_MEMBERS, {
            query: { select: "*", nome: `ilike.%${cleanName}%`, limit: "5" }
          });
          if (Array.isArray(fetchedIlike) && fetchedIlike.length > 0) {
            fetchedIlike.forEach(m => visitMembers.push(m));
          }
        }
      } catch (e) {
        console.error("Falha ao buscar membro por nome:", e);
      }
    }
  }

  const enriched = rows.map(visit => {
    const cleanName = String(visit.titulo || "").replace(/^visita\s*-\s*/i, "").replace(/^visita\s+/i, "").trim();
    const member = visitMembers.find(m => String(m.id) === String(visit.irmandade_id || ""))
      || visitMembers.find(m => normalize(m.nome) === normalize(cleanName))
      || visitMembers.find(m => normalize(m.nome).includes(normalize(cleanName)) || normalize(cleanName).includes(normalize(m.nome)));

    const memberPhone = getMemberPhone(member);
    const phone = visit.celular || visit.telefone || memberPhone;
    const tel = visit.telefone || memberPhone || phone;

    return {
      ...visit,
      celular: phone,
      telefone: tel,
      comum: visit.comum || member?.comum || "",
      setor: visit.setor || member?.setor || "",
      categoria: visit.categoria || member?.categoria || "GVI",
      preferencia_periodo_visita: member?.preferencia_periodo_visita || "",
      classificacao_adicional: member?.classificacao_adicional || "",
      periodo_planejado: plannedPeriodFromNotes(visit.observacoes),
      horario_inicio: startTimeFromNotes(visit.observacoes),
      horario_fim: endTimeFromNotes(visit.observacoes),
      observacoes: visibleVisitNotes(visit.observacoes),
      municipio: visit.municipio || visit.cidade || member?.cidade || member?.municipio || "",
      ...(context.canViewRestrictedNotes && member?.apontamentos_restritos
        ? { apontamentos_restritos: member.apontamentos_restritos }
        : {})
    };
  });

  return enriched.filter(visit => visitMatchesSelectedScope(context, visit)
    && (context.isGlobal || personalVisitAccess(context, visit)));

}

async function assertVisitAccess(context, visitId) {
  const rows = await supabase(TABLE_AGENDA, { query: { select: "*", id: `eq.${visitId}`, limit: "1" } });
  const visit = rows[0];
  if (!visit) {
    throw Object.assign(new Error("Esta visita não pertence à sua equipe."), { status: 403 });
  }
  // A atribuição da visita à equipe é a fonte de autorização. A comum do
  // cadastro visitado não pode ser inferida do endereço/bairro, nem um ID de
  // irmandade legado deve invalidar um item que já pertence ao roteiro.
  // Prefira o vínculo estável por UUID; para registros antigos, normalize
  // "Equipe 1" e "Equipe 01" da mesma forma usada pela listagem.
  const assignedMembers = visit.irmandade_id ? await supabase(TABLE_MEMBERS, { query: { select: "*", id: `eq.${visit.irmandade_id}`, limit: "1" } }) : [];
  if (!personalVisitAccess(context, visit, assignedMembers[0])) {
    throw Object.assign(new Error("Esta visita não pertence à sua equipe."), { status: 403 });
  }
  return visit;
}

async function login(req, res) {
  requiredConfig();
  const body = await readJson(req);
  const response = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: SUPABASE_ANON_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ email: String(body.email || "").trim(), password: body.password || "" })
  });
  const payload = await response.json();
  if (!response.ok) return sendJson(res, 401, { error: "E-mail ou senha incorretos." });
  return sendJson(res, 200, {
    access_token: payload.access_token, refresh_token: payload.refresh_token,
    expires_in: payload.expires_in, user: { id: payload.user?.id, email: payload.user?.email }
  });
}

async function refreshSession(req, res) {
  requiredConfig();
  const body = await readJson(req);
  if (!body?.refresh_token) return sendJson(res, 400, { error: "Refresh token é obrigatório." });
  const response = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=refresh_token`, {
    method: "POST",
    headers: { apikey: SUPABASE_ANON_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: String(body.refresh_token) })
  });
  const payload = await response.json();
  if (!response.ok) return sendJson(res, 401, { error: "Sessão expirada. Faça login novamente." });
  return sendJson(res, 200, {
    access_token: payload.access_token,
    refresh_token: payload.refresh_token,
    expires_in: payload.expires_in,
    user: { id: payload.user?.id, email: payload.user?.email }
  });
}

function requestOrigin(req) {
  const forwardedProto = String(req.headers["x-forwarded-proto"] || "").split(",")[0].trim();
  const protocol = forwardedProto || (req.socket?.encrypted ? "https" : "http");
  const forwardedHost = String(req.headers["x-forwarded-host"] || "").split(",")[0].trim();
  const host = forwardedHost || String(req.headers.host || "localhost");
  return `${protocol}://${host}`;
}

async function requestPasswordRecovery(req, res) {
  requiredConfig();
  const body = await readJson(req);
  const email = String(body.email || "").trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) return sendJson(res, 400, { error: "Informe um e-mail válido." });
  const redirectTo = PASSWORD_RECOVERY_REDIRECT_URL || `${requestOrigin(req)}/redefinir-senha`;
  const response = await fetch(`${SUPABASE_URL}/auth/v1/recover?redirect_to=${encodeURIComponent(redirectTo)}`, {
    method: "POST", headers: { apikey: SUPABASE_ANON_KEY, "Content-Type": "application/json" }, body: JSON.stringify({ email })
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    console.error("password_recovery_error", payload?.msg || payload?.message || response.statusText);
    if (response.status === 429) return sendJson(res, 429, { error: "Aguarde um momento antes de solicitar outro link." });
    throw Object.assign(new Error("Não foi possível enviar o link agora. Tente novamente."), { status: 502 });
  }
  return sendJson(res, 200, { message: "Se o e-mail estiver cadastrado, você receberá um link para redefinir sua senha." });
}

async function updateRecoveredPassword(req, res) {
  requiredConfig();
  let token = bearer(req);
  const body = await readJson(req);
  const password = String(body.password || "");
  const tokenHash = String(body.token_hash || "").trim();
  if (password.length < 6) return sendJson(res, 400, { error: "A senha deve ter pelo menos 6 caracteres." });
  if (!token && tokenHash) {
    const verification = await fetch(`${SUPABASE_URL}/auth/v1/verify`, {
      method: "POST",
      headers: { apikey: SUPABASE_ANON_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ token_hash: tokenHash, type: "recovery" })
    });
    const session = await verification.json().catch(() => ({}));
    if (!verification.ok || !session.access_token) {
      return sendJson(res, 401, { error: "Este link de recuperação expirou ou já foi utilizado. Solicite um novo link." });
    }
    token = session.access_token;
  }
  if (!token) return sendJson(res, 401, { error: "O link de recuperação expirou ou é inválido." });
  const response = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
    method: "PUT", headers: { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({ password })
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const message = [401, 403].includes(response.status) ? "Este link de recuperação expirou ou já foi utilizado. Solicite um novo link." : "Não foi possível atualizar a senha agora. Tente novamente.";
    return sendJson(res, response.status === 401 ? 401 : 400, { error: message });
  }
  return sendJson(res, 200, { message: "Senha atualizada com sucesso." });
}


async function handleApi(req, res, url) {
  const pathname = url.pathname;
  if (req.method === "POST" && pathname === "/api/mobile/login") return login(req, res);
  if (req.method === "POST" && pathname === "/api/mobile/refresh") return refreshSession(req, res);
  if (req.method === "POST" && pathname === "/api/mobile/recuperar-senha") return requestPasswordRecovery(req, res);
  if (req.method === "POST" && pathname === "/api/mobile/redefinir-senha") return updateRecoveredPassword(req, res);

  const context = await mobileContext(req, url);
  if (req.method === "GET" && pathname === "/api/mobile/context") {
    return sendJson(res, 200, {
      usuario: context.profile.full_name || context.member.nome,
      membro: context.member.nome, comum: context.comum,
      municipio: context.municipio, equipe: context.teams.map(t => t.equipe).join(" + "),
      isGlobal: context.isGlobal,
      teams: context.teams,
      assignmentMissing: !context.teams.length,
      accessLevel: context.level,
      canDeleteVisits: new Set(["global", "regional"]).has(context.level),
      canHighlightExcessDuration: context.canHighlightExcessDuration,
      canViewRestrictedNotes: context.canViewRestrictedNotes,
      members: context.members.map(m => ({ id: m.id, nome: m.nome, endereco: m.endereco }))
    });
  }
  if (req.method === "GET" && pathname === "/api/mobile/comuns") {
    try {
      const cRows = await supabase("visitas_comuns", { query: { select: "comum,cidade", order: "comum.asc", limit: "500" } }).catch(() => []);
      let rawList = Array.isArray(cRows) && cRows.length > 0 ? cRows : [];
      if (!rawList.length) {
        const mRows = await supabase(TABLE_MEMBERS, { query: { select: "comum,cidade", limit: "2500" } }).catch(() => []);
        rawList = Array.isArray(mRows) ? mRows : [];
      }
      const list = rawList.map(r => ({
        comum: String(r.comum || "").trim(),
        cidade: String(r.cidade || r.municipio || "").trim()
      })).filter(r => r.comum);

      const distinctComuns = Array.from(new Set(list.map(r => r.comum))).sort();
      const distinctCidades = Array.from(new Set(list.map(r => r.cidade).filter(Boolean))).sort();

      return sendJson(res, 200, { comuns: list, distinctComuns, cidades: distinctCidades });
    } catch {
      return sendJson(res, 200, { comuns: [{ comum: context.comum, cidade: context.municipio }], distinctComuns: [context.comum], cidades: [context.municipio] });
    }
  }
  if (req.method === "GET" && pathname === "/api/mobile/visitas") {
    const date = validDate(url.searchParams.get("data"));
    const visits = await teamVisits(context, date);
    return sendJson(res, 200, { data: date, equipe: context.equipe, comum: context.comum, visitas: visits });
  }

  const periodMatch = pathname.match(/^\/api\/mobile\/visitas\/([0-9a-f-]+)\/periodo$/i);
  if (req.method === "PATCH" && periodMatch) {
    const visit = await assertVisitAccess(context, periodMatch[1]);
    const body = await readJson(req);
    const period = String(body.periodo || "").trim().toLowerCase();
    if (!new Set(["manha", "tarde", "noite"]).has(period)) {
      throw Object.assign(new Error("Período inválido. Escolha manhã, tarde ou noite."), { status: 400 });
    }
    if (visit.status !== "Marcada") {
      throw Object.assign(new Error("Somente visitas agendadas podem ser remanejadas."), { status: 400 });
    }

    const updated = await supabase(TABLE_AGENDA, {
      method: "PATCH", query: { id: `eq.${periodMatch[1]}` }, prefer: "return=representation",
      body: { observacoes: notesWithPlannedPeriod(visit.observacoes, period) }
    });
    return sendJson(res, 200, {
      message: `Visita classificada no período da ${period === "manha" ? "manhã" : period === "tarde" ? "tarde" : "noite"}.`,
      visita: updated?.[0] || null
    });
  }

  const visitMatch = pathname.match(/^\/api\/mobile\/visitas\/([0-9a-f-]+)$/i);
  if (req.method === "DELETE" && visitMatch) {
    if (!new Set(["global", "regional"]).has(context.level)) {
      throw Object.assign(new Error("Somente usuários globais e regionais podem excluir visitas."), { status: 403 });
    }
    const currentVisit = await assertVisitAccess(context, visitMatch[1]);
    if (currentVisit.status !== "Marcada") {
      throw Object.assign(new Error("Somente visitas agendadas podem ser excluídas."), { status: 409 });
    }
    await supabase(TABLE_AGENDA, {
      method: "DELETE", query: { id: `eq.${visitMatch[1]}` }, prefer: "return=representation"
    });
    return sendJson(res, 200, { message: "Visita excluída com sucesso." });
  }
  if (req.method === "PATCH" && visitMatch) {
    const currentVisit = await assertVisitAccess(context, visitMatch[1]);
    const body = await readJson(req);
    const allowed = new Set(["Realizada", "Cancelada", "Não realizada"]);
    if (!allowed.has(body.status)) throw Object.assign(new Error("Selecione um status válido."), { status: 400 });
    const motivo = String(body.motivo || "").trim();
    if (body.status !== "Realizada" && !motivo) {
      throw Object.assign(new Error("Informe o motivo da visita não ter sido realizada."), { status: 400 });
    }
    const requestedNotes = String(body.observacoes || "").trim();
    const existingPeriod = plannedPeriodFromNotes(currentVisit.observacoes);
    const requestedStartTime = String(body.horario_inicio || "").trim();
    const requestedEndTime = String(body.horario_fim || "").trim();
    const validTime = value => /^([01]\d|2[0-3]):[0-5]\d$/.test(value);
    if ((requestedStartTime && !validTime(requestedStartTime)) || (requestedEndTime && !validTime(requestedEndTime))) {
      throw Object.assign(new Error("Informe horários válidos."), { status: 400 });
    }
    if (body.status === "Realizada" && Boolean(requestedStartTime) !== Boolean(requestedEndTime)) {
      throw Object.assign(new Error("Preencha os horários de início e fim, ou deixe ambos vazios."), { status: 400 });
    }
    if (requestedStartTime && requestedEndTime && requestedEndTime <= requestedStartTime) {
      throw Object.assign(new Error("O horário de fim deve ser posterior ao horário de início."), { status: 400 });
    }
    const startTime = body.status === "Realizada" ? requestedStartTime : "";
    const endTime = body.status === "Realizada" ? requestedEndTime : "";
    const selectedHour = startTime ? Number(startTime.slice(0, 2)) : null;
    const selectedPeriod = selectedHour === null ? existingPeriod : selectedHour < 12 ? "manha" : selectedHour < 18 ? "tarde" : "noite";
    const updateBody = {
      status: body.status,
      motivo_cancelamento: body.status === "Realizada" ? null : motivo,
      observacoes: notesWithVisitMetadata(requestedNotes, selectedPeriod, startTime, endTime) || null
    };
    // O calendário principal usa data_inicio/data_fim como fonte do horário.
    // Quando o usuário informa o horário real, preservamos a data agendada e
    // substituímos somente as horas. Sem horários informados, os valores
    // originais não entram no PATCH e permanecem inalterados no banco.
    if (startTime && endTime) {
      const visitDate = new Intl.DateTimeFormat("en-CA", {
        timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit", day: "2-digit"
      }).format(new Date(currentVisit.data_inicio));
      updateBody.data_inicio = new Date(`${visitDate}T${startTime}:00-03:00`).toISOString();
      updateBody.data_fim = new Date(`${visitDate}T${endTime}:00-03:00`).toISOString();
    }
    const updated = await supabase(TABLE_AGENDA, {
      method: "PATCH", query: { id: `eq.${visitMatch[1]}` }, prefer: "return=representation",
      body: updateBody
    });
    return sendJson(res, 200, { message: "Visita atualizada com sucesso.", visita: updated?.[0] || null });
  }

  if (req.method === "POST" && pathname === "/api/mobile/irmandade") {
    const body = await readJson(req);
    const nome = String(body.nome || "").trim();
    const endereco = String(body.endereco || "").trim();
    if (!nome || !endereco) throw Object.assign(new Error("Informe o nome e o endereço da família."), { status: 400 });

    const targetComum = String(body.comum || url.searchParams.get("comum") || context.comum || "").trim();
    // A cidade residencial vem do CEP. O município administrativo usado para
    // listar a visita é determinado pela comum e não sobrescreve o endereço.
    const targetMunicipio = String(body.cidade_residencial || body.cidade || body.municipio || context.municipio || "").trim();

    const sameRegistration = item =>
      normalize(item.nome) === normalize(nome)
      && normalize(item.comum) === normalize(targetComum || context.comum)
      && normalizeAddress(item.endereco) === normalizeAddress(endereco);

    let member = context.members.find(sameRegistration);
    if (!member) {
      const existing = await supabase(TABLE_MEMBERS, {
        query: {
          select: "*", nome: `eq.${nome}`,
          comum: `eq.${targetComum || context.comum}`, limit: "100"
        }
      }).catch(() => []);
      if (Array.isArray(existing)) member = existing.find(sameRegistration) || null;
    }

    if (!member) {
      const created = await supabase(TABLE_MEMBERS, {
        method: "POST", prefer: "return=representation", body: {
          nome,
          comum: targetComum || context.comum,
          cidade: targetMunicipio || context.municipio,
          setor: String(body.setor || "").trim() || null,
          endereco,
          complemento: String(body.complemento || "").trim() || null,
          cep: String(body.cep || "").trim() || null,
          celular: String(body.celular || "").trim() || null,
          observacoes: String(body.observacoes || "").trim() || null,
          equipe_id: null,
          equipe_visita: null,
          grupo_regional_id: null,
          grupo_regional_nome: null,
          status: "Ativo", origem_registro: "App Mobile - Visita em campo"
        }
      });
      member = created?.[0];
    }
    if (!member?.id) throw Object.assign(new Error("O cadastro foi salvo sem identificação."), { status: 502 });

    const scheduleRequested = truthy(body.agendar_visita);
    if (!scheduleRequested) {
      return sendJson(res, 201, {
        message: "Cadastro realizado com sucesso.", membro: member, visita: null
      });
    }
    if (!context.equipe) {
      throw Object.assign(new Error("Seu usuário não possui uma equipe de visitas vinculada para realizar o agendamento."), { status: 400 });
    }

    // O agendamento só é criado quando solicitado explicitamente no cadastro.
    const visitStatus = "Marcada";
    const scheduledDate = validDate(body.data);
    const scheduledTime = String(body.hora || body.horario || "20:00").trim();
    const scheduledMatch = scheduledTime.match(/^(\d{1,2}):(\d{2})$/);
    const scheduledHour = scheduledMatch ? scheduledMatch[1].padStart(2, "0") : "20";
    const scheduledMinute = scheduledMatch ? scheduledMatch[2] : "00";
    const start = body.data_inicio
      ? new Date(body.data_inicio)
      : new Date(`${scheduledDate}T${scheduledHour}:${scheduledMinute}:00-03:00`);
    const end = new Date(start.getTime() + 45 * 60 * 1000);
    const appointmentDate = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(start);
    await requireNoSameDayFamilyVisit(member, context, appointmentDate);
    await requireRecentVisitConfirmation(body, member, context, start);
    const agendaBody = {
      irmandade_id: member.id, titulo: nome, data_inicio: start.toISOString(), data_fim: end.toISOString(),
      equipe_responsavel: context.equipe, equipe_id: context.equipeId || null, equipe_tipo: context.teamType,
      categoria: String(body.categoria || "GVI").trim(), status: visitStatus,
      motivo_cancelamento: String(body.motivo || "").trim() || null,
      setor: String(body.setor || "").trim() || null, endereco_visitado: endereco,
      observacoes: String(body.observacoes || "Cadastro realizado via App Mobile.").trim()
    };
    const agenda = await supabase(TABLE_AGENDA, {
      method: "POST", prefer: "return=representation", body: agendaBody
    });
    return sendJson(res, 201, { message: "Cadastro realizado e visita agendada no roteiro!", membro: member, visita: agenda?.[0] });
  }

  if (req.method === "POST" && pathname === "/api/mobile/agendar") {
    const body = await readJson(req);
    const irmandade_id = String(body.irmandade_id || "").trim();
    if (!irmandade_id) {
      throw Object.assign(new Error("Selecione a pessoa correta na lista antes de agendar."), { status: 400 });
    }
    if (!context.equipe) {
      throw Object.assign(new Error("Seu usuário não possui uma equipe de visitas vinculada para realizar o agendamento."), { status: 400 });
    }

    let member = null;
    if (irmandade_id) {
      member = context.members.find(m => String(m.id) === irmandade_id);
      if (!member) {
        const fetched = await supabase(TABLE_MEMBERS, {
          query: { select: "*", id: `eq.${irmandade_id}`, limit: "1" }
        }).catch(() => []);
        member = Array.isArray(fetched) && fetched.length > 0 ? fetched[0] : null;
      }
    }

    if (!member) {
      throw Object.assign(new Error("A pessoa selecionada não foi encontrada nesta comum. Atualize a lista e tente novamente."), { status: 404 });
    }

    const data = validDate(body.data);
    const timeVal = String(body.hora || body.horario || "20:00").trim();
    const timeMatch = timeVal.match(/^(\d{1,2}):(\d{2})$/);
    const hour = timeMatch ? timeMatch[1].padStart(2, "0") : "20";
    const minute = timeMatch ? timeMatch[2] : "00";
    const start = new Date(`${data}T${hour}:${minute}:00-03:00`);
    const end = new Date(start.getTime() + 60 * 60 * 1000);
    const categoria = String(body.categoria || "GVI").trim();
    await requireNoSameDayFamilyVisit(member, context, data);
    await requireRecentVisitConfirmation(body, member, context, start);

    const agendaBody = {
      irmandade_id: member.id, titulo: member.nome, data_inicio: start.toISOString(), data_fim: end.toISOString(),
      equipe_responsavel: context.equipe, equipe_id: context.equipeId || null, equipe_tipo: context.teamType,
      categoria, status: "Marcada",
      setor: member.setor || null, endereco_visitado: member.endereco || "",
      observacoes: String(body.observacoes || "").trim() || null
    };
    const agenda = await supabase(TABLE_AGENDA, {
      method: "POST", prefer: "return=representation", body: agendaBody
    });
    return sendJson(res, 201, { message: "Visita agendada com sucesso.", visita: agenda?.[0] });
  }

  return sendJson(res, 404, { error: "Rota não encontrada." });
}

async function serveStatic(pathname, res) {
  const legacyPages = new Set(["/cadastro.html", "/registro.html", "/presenca.html", "/cadastro", "/registro", "/presenca"]);
  if (legacyPages.has(pathname)) {
    res.writeHead(302, { Location: "/", "Cache-Control": "no-store" });
    res.end();
    return;
  }
  const routes = { "/": "index.html", "/login": "login.html", "/login.html": "login.html", "/recuperar-senha": "recuperar-senha.html", "/recuperar-senha.html": "recuperar-senha.html", "/redefinir-senha": "redefinir-senha.html", "/redefinir-senha.html": "redefinir-senha.html" };
  const relative = routes[pathname] || pathname.replace(/^\//, "");
  const file = path.resolve(publicDir, relative);
  if (!file.startsWith(path.resolve(publicDir)) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    return sendJson(res, 404, { error: "Página não encontrada." });
  }
  res.writeHead(200, {
    "Content-Type": mimeTypes[path.extname(file).toLowerCase()] || "application/octet-stream",
    "Cache-Control": relative.endsWith(".html") ? "no-store" : "public, max-age=300"
  });
  fs.createReadStream(file).pipe(res);
}

async function handleRequest(req, res) {
  try {
    const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
    if (url.pathname.startsWith("/api/mobile/")) return await handleApi(req, res, url);
    if (req.method === "GET") return serveStatic(url.pathname, res);
    return sendJson(res, 405, { error: "Método não permitido." });
  } catch (error) {
    if (!new Set(["RECENT_FAMILY_VISIT", "DUPLICATE_FAMILY_VISIT_SAME_DAY"]).has(error.code)) {
      console.error("mobile_error", error.message, error.details || "");
    }
    const responseBody = { error: error.message || "Erro interno do servidor." };
    if (error.code) responseBody.code = error.code;
    if (error.recentVisit) responseBody.visita_recente = error.recentVisit;
    if (error.existingVisit) responseBody.visita_existente = error.existingVisit;
    return sendJson(res, Number(error.status) || 500, responseBody);
  }
}

module.exports = handleRequest;
module.exports._test = { visitMatchesSelectedScope, mobileContext, teamVisits, identifyMember, personalVisitAccess, normalizeTeam, teamAssignments, resolveTeamAssignment, visitBelongsToContextTeam, findSameDayFamilyVisit };

if (require.main === module) {
  http.createServer(handleRequest).listen(PORT, () => console.log(`App Visitas Mobile: http://localhost:${PORT}`));
}
