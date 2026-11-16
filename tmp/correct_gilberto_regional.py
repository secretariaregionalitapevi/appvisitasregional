from django.test import RequestFactory
from ColorAdminApp.admin_views import _get_table, _update_profile_via_rpc
from ColorAdminApp.views import log_audit
from ColorAdminApp.modules.access_control import user_scope
from ColorAdminApp.modules.music_exams import fetch_rows, fetch_legacy

uid = 'c57628fc-e259-41a6-b3c4-b193532d25db'
before = _get_table('profiles', {'user_id':'eq.'+uid,'select':'user_id,full_name,status,role_id,role,sector,municipio,comum','limit':'1'})[0]
assert before['full_name'] == 'Gilberto Ferreira'
changes = {'role_id':2,'role':'Admin'}
updated = _update_profile_via_rpc(uid, changes)
assert updated['role_id'] == 2
request = RequestFactory().post('/maintenance/user-regional-scope/')
request.session = {'user_profile':{'full_name':'Correção técnica assistida','role':'Sistema'}}
log_audit(request, 'USER_ACCESS_SCOPE_CORRECTED', 'ADMIN', {
    'target_user_id':uid,'authorization':'Usuário solicitou corrigir o acesso de Gilberto Ferreira para Regional.',
    'before':{'role_id':before['role_id'],'role':before['role']},'after':changes})
after = _get_table('profiles', {'user_id':'eq.'+uid,'select':'user_id,status,role_id,role,sector,municipio,comum','limit':'1'})[0]
assert after['role_id'] == 2
request.session = {'user_id':uid,'user_profile':after}
assert user_scope(request)['level'] == 'regional'
print('PERFIL_CONFIRMADO', {'role_id':after['role_id'],'scope':user_scope(request)['level']})
print('EXAMES_VISIVEIS', {'individuais':len(fetch_rows(request)), 'lancamentos':len(fetch_legacy(request))})
