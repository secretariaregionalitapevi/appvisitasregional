const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('ColorAdminApp/templates/pages/visitas-dashboard.html', 'utf8');
const helpers = html.slice(html.indexOf('    const agendaTeamType'), html.indexOf('    const saoPauloDayStart'));
const render = html.slice(html.indexOf('    const renderDashboards'), html.indexOf('    const renderTrendChart'));
const values = {};
let rows;
let selectedCommon = ''; 
const sandbox = {
    dashboardGroupContext: 'LOCAL', dashboardAccessLevel: 'global', console,
    formatNum: n => String(n || 0),
    $: key => ({val: () => selectedCommon, text: value => { values[key] = value; return {toggleClass(){}}; }, html: value => {values[key] = value;}}),
    moment: value => {const d = new Date(value); return {isValid: () => !isNaN(d), month: () => d.getUTCMonth(), year: () => d.getUTCFullYear()};},
    renderTrendChart: agenda => assert(agenda.every(v => v.status === 'Realizada')),
    renderMixChart(){}, renderRankingList(){}, renderTable: result => { rows = result; },
};
vm.createContext(sandbox);
vm.runInContext(helpers + render + '\nthis.run = renderDashboards;', sandbox);
const monthly = [{referencia_mes:10, referencia_ano:2026, comum:'BR-22-0673 - VILA', gvi:120, gvm:0, gve:0, rf:0, re:0}];
const visit = (categoria, extra={}) => ({categoria, comum:'BR-22-0673 - Vila', data_inicio:'2026-10-01T20:00:00-03:00', status:'Realizada', ...extra});
sandbox.run(monthly, [visit('RF'), visit('RE'), visit('Músicos'), visit('Organistas'), visit('GVI'), visit('RF',{status:'Agendada'}), visit('RE',{status:'Cancelada'}), visit('GVE',{status:'Não realizada'})]);
assert.equal(values['#kpi-total'],'5');
assert.equal(values['#kpi-gve'],'2');
assert.equal(values['#kpi-rf'],'1');
assert.equal(values['#kpi-re'],'1');
assert.equal(rows[0].total_visitas,5);
sandbox.run([{...monthly[0], rf:20, re:5, gve:14}], [visit('RF'),visit('RE'),visit('GVE')]);
assert.equal(values['#kpi-total'],'3');
sandbox.run([], [visit('RF'),visit('GVE'),visit('RE',{status:'Agendada'})]);
assert.equal(values['#kpi-total'],'2');
sandbox.dashboardGroupContext = 'ALL';
sandbox.run(monthly,[visit('GVI',{equipe_tipo:'REGIONAL'}),visit('GVI')]);
assert.equal(values['#kpi-total'],'2');
sandbox.dashboardGroupContext = 'REGIONAL';
sandbox.run(monthly,[visit('RF'),visit('GVE',{equipe_tipo:'REGIONAL'})]);
assert.equal(values['#kpi-total'],'1');
sandbox.dashboardGroupContext = 'LOCAL';
selectedCommon = 'BR-22-0673 - Vila';
sandbox.run(monthly, [visit('GVI'), visit('GVI',{comum:'BR-22-9999 - OUTRA'}), visit('RF',{status:'Agendada'})]);
assert.equal(values['#kpi-total'],'1');
assert.equal(values['#ops-realizadas'],'1');
assert.equal(rows.length,1);
sandbox.run(monthly, []);
assert.equal(values['#kpi-total'],'0');
console.log('Isolamento por comum e fechamento sem agenda: aprovados.');
