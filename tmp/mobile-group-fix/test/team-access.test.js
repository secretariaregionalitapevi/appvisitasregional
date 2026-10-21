const test = require("node:test");
const assert = require("node:assert/strict");
const { resolveTeamAssignment, visitBelongsToContextTeam, findSameDayFamilyVisit } = require("../src/server")._test;

test("registered member without a team cannot inherit stale profile team", () => {
  const assignment = resolveTeamAssignment(true, {}, { equipe_id: "team-1", equipe_visita: "Equipe 1" });
  assert.equal(assignment.equipe, "");
  assert.equal(assignment.equipeId, null);
});

test("registered local member receives only the assigned team", () => {
  const assignment = resolveTeamAssignment(true, { equipe_id: "team-2", equipe_visita: "Equipe 2" }, {});
  assert.deepEqual(assignment, { equipe: "Equipe 2", equipeId: "team-2", teamType: "LOCAL" });
  assert.equal(visitBelongsToContextTeam(assignment, { equipe_id: "team-2", equipe_responsavel: "Equipe 2" }), true);
  assert.equal(visitBelongsToContextTeam(assignment, { equipe_id: "team-3", equipe_responsavel: "Equipe 2" }), false);
});

test("legacy team names normalize Equipe 1 and Equipe 01", () => {
  const context = { equipe: "Equipe 2", equipeId: null };
  assert.equal(visitBelongsToContextTeam(context, { equipe_responsavel: "Equipe 02" }), true);
  assert.equal(visitBelongsToContextTeam(context, { equipe_responsavel: "Equipe 3" }), false);
});

test("context without a team cannot access any visit", () => {
  assert.equal(visitBelongsToContextTeam({ equipe: "", equipeId: null }, { equipe_responsavel: "Equipe 1" }), false);
});

test("profile team never grants agenda access without a registered member", () => {
  const assignment = resolveTeamAssignment(false, {}, { grupo_regional_id: "group-a", grupo_regional_nome: "Grupo A" });
  assert.deepEqual(assignment, { equipe: "", equipeId: null, teamType: "LOCAL" });
});

test("same-day visit for the same family is found by member or normalized address", () => {
  const member = { id: "member-1", nome: "Maria", endereco: "Rua São João, 10" };
  const sameAddressVisit = {
    id: "address-match", irmandade_id: "member-2", endereco_visitado: "Rua Sao Joao 10",
    data_inicio: "2026-10-02T18:00:00Z", status: "Marcada", equipe_responsavel: "Grupo 2"
  };
  const sameMemberVisit = {
    id: "member-match", irmandade_id: "member-1", data_inicio: "2026-10-02T18:00:00Z", status: "Marcada"
  };

  assert.equal(findSameDayFamilyVisit([sameAddressVisit], member, ["member-1"], "2026-10-02")?.id, "address-match");
  assert.equal(findSameDayFamilyVisit([sameMemberVisit], member, ["member-1"], "2026-10-02")?.id, "member-match");
});

test("same-day visit lookup ignores another date and canceled visits", () => {
  const member = { id: "member-1", endereco: "Rua São João, 10" };
  const visits = [
    { id: "canceled", irmandade_id: "member-1", data_inicio: "2026-10-02T12:00:00-03:00", status: "Cancelada" },
    { id: "other-day", irmandade_id: "member-1", data_inicio: "2026-10-03T12:00:00-03:00", status: "Marcada" }
  ];

  assert.equal(findSameDayFamilyVisit(visits, member, ["member-1"], "2026-10-02"), null);
});
const { teamAssignments } = require("../src/server")._test;
test("dual assignment exposes local and regional routes", () => {
  const teams = teamAssignments(true, { equipe_id: "l", equipe_visita: "Equipe 1", grupo_regional_id: "r", grupo_regional_nome: "Grupo A" });
  assert.deepEqual(teams.map(t => t.key), ["local", "regional"]);
  assert.equal(visitBelongsToContextTeam(teams[1], { equipe_id: "r", equipe_tipo: "REGIONAL" }), true);
  assert.equal(visitBelongsToContextTeam(teams[1], { equipe_responsavel: "Grupo A" }), true);
  assert.equal(visitBelongsToContextTeam(teams[1], { equipe_id: "other", equipe_responsavel: "Grupo A" }), false);
  assert.equal(visitBelongsToContextTeam(teams[1], { equipe_responsavel: "Grupo A", equipe_tipo: "LOCAL" }), false);
});
test("unregistered member cannot select a regional route", () => {
  assert.deepEqual(teamAssignments(false, { grupo_regional_nome: "Grupo A" }), []);
});

const { personalVisitAccess, identifyMember, teamVisits } = require("../src/server")._test;
test("personal route combines both registered teams regardless of destination filter", () => {
  const context = { comum: "Other selected common", teams: [
    { equipe: "Equipe 1", equipeId: "local-id", teamType: "LOCAL", comum: "Home" },
    { equipe: "Grupo A", equipeId: "regional-id", teamType: "REGIONAL", municipio: "ITAPEVI" }
  ] };
  assert.equal(personalVisitAccess(context, { equipe_id: "regional-id", equipe_tipo: "REGIONAL" }, { comum: "Destination", cidade: "Itapevi" }), true);
  assert.equal(personalVisitAccess(context, { equipe_id: "local-id", equipe_tipo: "LOCAL" }, { comum: "Home" }), true);
  assert.equal(personalVisitAccess(context, { equipe_id: "local-id", equipe_tipo: "LOCAL" }, { comum: "Other" }), false);
  assert.equal(personalVisitAccess(context, { equipe_id: "regional-id", equipe_tipo: "REGIONAL" }, { cidade: "Other city" }), false);
  assert.equal(personalVisitAccess(context, { equipe_id: "foreign", equipe_responsavel: "Grupo A" }, {}), false);
  assert.equal(personalVisitAccess(context, { equipe_responsavel: "Grupo A" }, {}), true);
});
test("identity accepts unique registered full name independently of selected destination", () => {
  const member = { id: "registered", nome: "Ricardo de Castro Grangeiro", comum: "Home" };
  assert.equal(identifyMember([member], "Ricardo Grangeiro", "Destination"), member);
  assert.equal(identifyMember([member, { ...member, id: "duplicate" }], "Ricardo Grangeiro", "Destination"), null);
});

test("login user email never becomes a query against the member registry", () => {
  const { spawnSync } = require("node:child_process");
  const modulePath = require.resolve("../src/server");
  const script = `
    const assert = require("node:assert/strict");
    process.env.SUPABASE_URL = "https://registry-test.invalid";
    process.env.SUPABASE_ANON_KEY = "test-anon";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "test-service";
    const { mobileContext, teamVisits } = require(${JSON.stringify(modulePath)})._test;
    const member = { id: "member", nome: "Ricardo de Castro Grangeiro", comum: "Home", cidade: "ITAPEVI", equipe_visita: "Equipe 1", equipe_id: "local", grupo_regional_nome: "Grupo A", grupo_regional_id: "regional" };
    global.fetch = async (input) => {
      const url = new URL(input);
      let data;
      if (url.pathname === "/auth/v1/user") data = { id: "user", email: "login@example.test" };
      else if (url.pathname.endsWith("/profiles")) data = [{ user_id: "user", full_name: "Ricardo Grangeiro", status: "approved", role_id: 1, comum: "Home", municipio: "ITAPEVI" }];
      else if (url.pathname.endsWith("/visitas_irmandade")) {
        assert.equal(url.searchParams.has("email"), false, "registry has no email column");
        data = [member];
      } else if (url.pathname.endsWith("/visitas_agenda")) data = [{ id: "visit", irmandade_id: "member", equipe_id: "regional", equipe_tipo: "REGIONAL", equipe_responsavel: "Grupo A", data_inicio: "2026-10-17T12:00:00Z", titulo: member.nome }];
      else throw Error("Unexpected request: " + url.pathname);
      return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    (async () => {
      const context = await mobileContext({ headers: { authorization: "Bearer test" } }, new URL("https://app.invalid/api/mobile/context?comum=Destination"));
      assert.equal(context.member.id, "member");
      assert.equal(context.teams.length, 2);
      const visits = await teamVisits(context, "2026-10-17");
      assert.equal(visits.length, 0, "selected destination excludes another common");
      context.comum = "Home";
      const homeVisits = await teamVisits(context, "2026-10-17");
      assert.equal(homeVisits.length, 1);
      assert.equal(homeVisits[0].equipe_responsavel, "Grupo A");
    })().catch(error => { console.error(error); process.exitCode = 1; });
  `;
  const result = spawnSync(process.execPath, ["-e", script], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
});

const { visitMatchesSelectedScope } = require("../src/server")._test;
test("selected common applies to global and local visits", () => {
  for (const isGlobal of [true, false]) {
    const context = { comum: "Selected", municipio: "ITAPEVI", isGlobal };
    assert.equal(visitMatchesSelectedScope(context, { comum: "Selected" }), true);
    assert.equal(visitMatchesSelectedScope(context, { comum: "Other" }), false);
    assert.equal(visitMatchesSelectedScope(context, {}), false);
  }
});
test("municipal access stays within the registered city", () => {
  const context = { level: "municipal", isGlobal: true, comum: "Selected", profile: { municipio: "ITAPEVI" } };
  assert.equal(visitMatchesSelectedScope(context, { comum: "Selected", municipio: "ITAPEVI" }), true);
  assert.equal(visitMatchesSelectedScope(context, { comum: "Selected", municipio: "Other" }), false);
});
test("team and supervision selector is absent from the route UI", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const source = fs.readFileSync(path.join(__dirname, "../public/scripts/visitas.js"), "utf8");
  assert.equal(source.includes("route-team"), false);
  assert.equal(source.includes("teamPicker"), false);
  assert.equal(source.includes("vinculo="), false);
});
