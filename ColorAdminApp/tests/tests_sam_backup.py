import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from uuid import uuid4

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve

from ColorAdminApp import sam_backup as backup, sam_backup_views as views


def document():
    return {"schema_version": 1, "id": str(uuid4()), "started_at": "2026-10-08T12:00:00+00:00",
            "finished_at": "2026-10-08T12:01:00+00:00", "tables": {name: [] for name in backup.TABLES}}


def fixture():
    d = document(); t = d["tables"]
    t["visitas_comuns"] = [{"comum": "BR-21-1111 - VILA DAS CHÁCARAS", "cidade": "ITAPEVI"},
                           {"comum": "BR-21-2222 - OUTRA COMUM", "cidade": "ITAPEVI"}]
    t["sam_gem_groups"] = [{"id": "g1", "source_id": 10, "congregacao": "VILA DAS CHÁCARAS", "turma": "Turma 1", "curso": "MSA", "matriculados": 1}]
    t["sam_gem_classes"] = [{"id": "c1", "source_id": 20, "turma_source_id": 10, "turma_id": "g1", "data_aula": "2026-01-01", "congregacao": "VILA DAS CHÁCARAS"}]
    t["sam_gem_enrollments"] = [{"id": "e1", "turma_id": "g1", "source_member_id": 30, "aluno_id": "s1", "nome_aluno": "ALUNO EXTERNO", "congregacao": "OUTRA COMUM"}]
    t["sam_gem_attendance"] = [{"id": "a1", "aula_id": "c1", "source_member_id": 30, "aluno_id": "s1", "presente": False, "nome_aluno": "ALUNO EXTERNO"}]
    t["musica_acompanhamento_aluno"] = [{"id": "s1", "nome_aluno": "ALUNO EXTERNO", "comum_congregacao": "OUTRA COMUM"}]
    t["sam_student_sync_state"] = [{"id": "ss1", "source_key": "30", "aluno_id": "s1", "source_common": "OUTRA COMUM", "sync_status": "synced"}]
    t["musica_acompanhamento_msa"] = [{"id": "h1", "aluno_id": "s1", "fase": "1", "data_aula": "2026-01-01"}]
    return d


class InventoryTests(SimpleTestCase):
    def test_expired_period_is_visible_even_when_sam_checkbox_is_active(self):
        d = fixture()
        d["tables"]["sam_gem_groups"][0].update(ativo=True, data_termino="2025-12-31")
        result = backup.inventory(d, "BR-21-1111")
        self.assertEqual(result["summary"]["finished_groups"], 1)
        self.assertEqual(result["summary"]["active_groups"], 0)
        self.assertEqual(result["groups"][0]["archive_status"], "Período encerrado")
        self.assertTrue(result["groups"][0]["ativo"])

    def test_finished_groups_are_preserved_but_not_authorized_for_restore(self):
        d = fixture()
        d["tables"]["sam_gem_groups"][0]["ativo"] = False
        result = backup.inventory(d, "BR-21-1111")
        self.assertEqual(result["summary"]["finished_groups"], 1)
        self.assertEqual(result["summary"]["active_groups"], 0)
        self.assertEqual(result["groups"][0]["archive_status"], "Finalizada")
        self.assertFalse(result["plan"]["sam_write_enabled"])
        self.assertEqual(result["plan"]["status"], "blocked")
        self.assertEqual(result["summary"]["history"], 1)

    def test_unknown_group_state_is_not_assumed_active(self):
        result = backup.inventory(fixture(), "BR-21-1111")
        self.assertEqual(result["summary"]["unconfirmed_groups"], 1)
        self.assertEqual(result["summary"]["active_groups"], 0)

    def test_external_student_is_included_by_class_location(self):
        result = backup.inventory(fixture(), "BR-21-1111")
        self.assertEqual(result["summary"]["students"], 1)
        self.assertEqual(result["summary"]["history"], 1)
        self.assertFalse(result["groups"][0]["classes"][0]["attendance"][0]["presente"])
        self.assertEqual(result["students"][0]["comum_congregacao"], "OUTRA COMUM")
        self.assertFalse(result["plan"]["sam_write_enabled"])
        self.assertEqual(result["plan"]["status"], "blocked")

    def test_br_identity_survives_changed_description(self):
        d = fixture(); d["tables"]["sam_gem_groups"][0]["congregacao"] = "BR-21-1111 - DESCRIÇÃO ANTIGA"
        self.assertEqual(backup.inventory(d, "BR-21-1111")["summary"]["groups"], 1)

    def test_ambiguous_names_are_not_merged(self):
        d = fixture(); d["tables"]["visitas_comuns"].append({"comum": "BR-21-3333 - VILA DAS CHÁCARAS", "cidade": "OUTRA CIDADE"})
        options, resolve_common = backup.locations(d["tables"])
        self.assertEqual(resolve_common("VILA DAS CHÁCARAS"), "VILA DAS CHACARAS")
        self.assertNotIn("VILA DAS CHACARAS", {r["key"] for r in options})
        _, _, pending = backup.locations(d["tables"], include_pending=True)
        self.assertIn("VILA DAS CHACARAS", {r["key"] for r in pending})
        self.assertEqual(backup.inventory(d, "BR-21-1111")["summary"]["groups"], 0)

    def test_orphans_and_conflicting_member_ids_block_review(self):
        d = fixture(); t=d["tables"]
        t["sam_gem_classes"][0].update(turma_id=None, turma_source_id=None)
        t["sam_student_sync_state"][0]["source_key"] = "99"
        t["sam_gem_attendance"][0]["presente"] = None
        result=backup.inventory(d, "BR-21-1111")
        codes={r["code"] for r in result["issues"]}
        self.assertTrue({"orphan_class", "source_identity", "attendance_value"}.issubset(codes))
        self.assertEqual(len(result["orphan_classes"]), 1)

    def test_class_source_id_can_resolve_missing_local_group_fk(self):
        d=fixture();d["tables"]["sam_gem_classes"][0]["turma_id"]=None
        result=backup.inventory(d,"BR-21-1111")
        self.assertEqual(len(result["groups"][0]["classes"]),1)

    def test_audit_ids_are_matched_with_entity_type(self):
        d=fixture();d["tables"]["sam_audit_events"]=[{"id":"log","target_type":"student","target_source_id":10,"congregation_snapshot":"OUTRA COMUM"}]
        self.assertEqual(backup.inventory(d,"BR-21-1111")["audit"],[])

    def test_unknown_common_is_rejected(self):
        with self.assertRaises(backup.BackupError): backup.inventory(fixture(),"UNKNOWN")


class ArchiveTests(SimpleTestCase):
    def test_roundtrip_and_never_overwrite(self):
        with TemporaryDirectory() as directory, override_settings(SAM_BACKUP_DIR=directory):
            saved=backup.save(fixture());self.assertEqual(backup.load(saved["id"]),saved)
            self.assertTrue(backup.list_archives()[0]["valid"])
            with self.assertRaises(FileExistsError): backup.save(saved)
            self.assertEqual(backup.load(saved["id"]),saved)
            self.assertEqual(len(list(Path(directory).glob("*.json.gz"))),1)
            self.assertEqual(list(Path(directory).glob("*.tmp")),[])

    def test_corrupted_archive_is_refused(self):
        with TemporaryDirectory() as directory, override_settings(SAM_BACKUP_DIR=directory):
            saved=backup.save(fixture());saved["tables"]["sam_gem_groups"][0]["turma"]="ALTERADA"
            path=Path(directory)/f"{saved['id']}.json.gz"
            path.write_bytes(gzip.compress(json.dumps(saved).encode()))
            with self.assertRaises(backup.BackupError): backup.load(saved["id"])
            self.assertFalse(backup.list_archives()[0]["valid"])

    def test_manifest_tampering_and_missing_tables_are_refused(self):
        saved=backup.seal(fixture());saved["finished_at"]="changed"
        with self.assertRaises(backup.BackupError):backup.verify(saved)
        d=document();d["tables"].pop("sam_gem_groups")
        with self.assertRaises(backup.BackupError):backup.save(d)

    def test_path_traversal_is_refused(self):
        with self.assertRaises(backup.BackupError):backup.load("../../other")

    @override_settings(IS_PRODUCTION=True)
    def test_ephemeral_production_storage_is_refused(self):
        with self.assertRaises(backup.BackupError):backup.save(document())


@override_settings(SUPABASE_URL="https://local-mirror.example",SUPABASE_SERVICE_ROLE_KEY="test-key")
class ReadTests(SimpleTestCase):
    def response(self, rows,total):
        response=Mock();response.ok=True;response.json.return_value=rows
        response.headers={"Content-Range":f"0-1/{total}"}
        return response

    @patch("ColorAdminApp.sam_backup.requests.get")
    def test_server_page_cap_does_not_truncate_archive(self,get):
        get.side_effect=[self.response([{"id":"1"},{"id":"2"}],3),self.response([{"id":"3"}],3)]
        rows=backup._read_table("sam_gem_groups")
        self.assertEqual(len(rows),3)
        self.assertEqual(get.call_args_list[1].kwargs["params"]["offset"],2)
        self.assertTrue(all(call.args[0].startswith("https://local-mirror.example/rest/v1/") for call in get.call_args_list))

    @patch("ColorAdminApp.sam_backup.requests.get")
    def test_changing_count_is_refused(self,get):
        get.side_effect=[self.response([{"id":"1"}],2),self.response([{"id":"2"}],3)]
        with self.assertRaises(backup.BackupError):backup._read_table("sam_gem_groups")

    @patch("ColorAdminApp.sam_backup.requests.get")
    def test_missing_exact_count_is_refused(self,get):
        response=self.response([],0);response.headers={};get.return_value=response
        with self.assertRaises(backup.BackupError):backup._read_table("sam_gem_groups")

    @patch("ColorAdminApp.sam_backup.requests.get")
    def test_repeated_id_is_refused(self,get):
        get.return_value=self.response([{"id":"1"},{"id":"1"}],2)
        with self.assertRaises(backup.BackupError):backup._read_table("sam_gem_groups")


class ViewTests(SimpleTestCase):
    def setUp(self):cache.clear();self.factory=RequestFactory()
    def request(self, method="get",role=1,params=None):
        request=getattr(self.factory,method)("/gem/sam/backup/",data=params or {})
        request.session={"authenticated":True,"user_profile":{"role_id":role},"user_id":"owner"}
        return request

    @patch("ColorAdminApp.sam_backup_views.sam_backup.capture")
    def test_non_owner_cannot_read_or_create_copy(self,capture):
        self.assertEqual(views.options(self.request(role=2)).status_code,403)
        self.assertEqual(views.archives(self.request("post",role=2)).status_code,403)
        capture.assert_not_called()

    @patch("ColorAdminApp.sam_backup_views.sam_backup.capture")
    def test_unauthenticated_owner_is_denied(self,capture):
        request=self.request();request.session["authenticated"]=False
        self.assertEqual(views.options(request).status_code,403);capture.assert_not_called()

    @patch("ColorAdminApp.sam_backup_views.sam_backup.capture")
    def test_post_to_read_endpoint_is_refused(self,capture):
        self.assertEqual(views.data(self.request("post")).status_code,405);capture.assert_not_called()

    @patch("ColorAdminApp.sam_backup_views.sam_backup.capture",side_effect=backup.BackupError("Incomplete"))
    @patch("ColorAdminApp.sam_backup_views.sam_backup.save")
    def test_failed_capture_never_saves(self,save,capture):
        self.assertEqual(views.archives(self.request("post")).status_code,503);save.assert_not_called()

    @patch("ColorAdminApp.sam_backup_views.sam_backup.capture",return_value=fixture())
    def test_create_and_consult_offline_copy(self,capture):
        with TemporaryDirectory() as directory,override_settings(SAM_BACKUP_DIR=directory):
            response=views.archives(self.request("post"));self.assertEqual(response.status_code,201)
            result=json.loads(response.content);capture.reset_mock()
            response=views.data(self.request(params={"backup":result["id"],"comum":"BR-21-1111"}))
            self.assertEqual(response.status_code,200);capture.assert_not_called()
            self.assertFalse(json.loads(response.content)["plan"]["sam_write_enabled"])
            download=views.download(self.request(),result["id"])
            self.assertIn("08-10-2026_09-01",download["Content-Disposition"])
            downloaded=b"".join(download.streaming_content);download.close()
            self.assertEqual(backup.verify(json.loads(gzip.decompress(downloaded)))["id"],result["id"])
            self.assertEqual(download["Cache-Control"],"no-store, private")

    def test_routes_resolve_without_restore_route(self):
        self.assertEqual(resolve("/gem/sam/backup/").url_name,"samBackup")
        self.assertEqual(resolve("/gem/sam/backup/copias/").url_name,"samBackupArchives")


class AdditionalSafetyTests(SimpleTestCase):
    @override_settings(SAM_BACKUP_DIR=None)
    def test_default_directory_is_outside_public_assets(self):
        self.assertEqual(backup.archive_dir().parts[-2:], (".backups", "sam"))

    def test_global_orphans_are_counted_without_assigning_to_a_common(self):
        d=fixture();d["tables"]["sam_gem_attendance"].append({"id":"orphan","aula_id":"missing","source_member_id":40})
        result=backup.inventory(d,"BR-21-1111")
        self.assertEqual(result["global_diagnostics"]["Chamadas sem aula preservada"],1)
        self.assertEqual(result["summary"]["attendance"],1)

    def test_archive_json_array_is_refused(self):
        with self.assertRaises(backup.BackupError):backup.verify([])

    def test_identity_from_attendance_alone_requires_review(self):
        d=fixture();d["tables"]["sam_student_sync_state"]=[]
        codes={row["code"] for row in backup.inventory(d,"BR-21-1111")["issues"]}
        self.assertIn("identity_evidence",codes)

    @patch("ColorAdminApp.sam_backup_views.sam_backup.capture")
    def test_invalid_archive_never_falls_back_to_live_capture(self,capture):
        request=RequestFactory().get("/gem/sam/backup/api/", {"backup":"../../missing","comum":"BR-21-1111"})
        request.session={"authenticated":True,"user_profile":{"role_id":1}}
        self.assertEqual(views.data(request).status_code,503);capture.assert_not_called()


class IndexSafetyTests(SimpleTestCase):
    def test_index_listing_checks_archive_without_loading_all_rows(self):
        with TemporaryDirectory() as directory,override_settings(SAM_BACKUP_DIR=directory):
            saved=backup.save(fixture())
            with patch("ColorAdminApp.sam_backup.load", side_effect=AssertionError("Full load unnecessary")):
                listed=backup.list_archives()
            self.assertTrue(listed[0]["valid"]);self.assertEqual(listed[0]["id"],saved["id"])

    def test_broken_index_is_rebuilt_from_verified_archive(self):
        with TemporaryDirectory() as directory,override_settings(SAM_BACKUP_DIR=directory):
            saved=backup.save(fixture())
            path=backup._archive_path(saved["id"])
            path.with_suffix(".index.json").write_text("broken",encoding="utf-8")
            self.assertTrue(backup.list_archives()[0]["valid"])
            self.assertEqual(backup.load(saved["id"]),saved)

    def test_copy_with_wrong_filename_is_refused(self):
        with TemporaryDirectory() as directory,override_settings(SAM_BACKUP_DIR=directory):
            saved=backup.save(fixture());other=str(uuid4())
            backup._archive_path(other).write_bytes(backup._archive_path(saved["id"]).read_bytes())
            with self.assertRaises(backup.BackupError):backup.load(other)

    def test_no_restore_endpoint_exists(self):
        from django.urls import Resolver404
        with self.assertRaises(Resolver404):resolve("/gem/sam/backup/restaurar/")


class MunicipalityResolutionTests(SimpleTestCase):
    def test_city_case_accents_and_spaces_do_not_duplicate_options(self):
        d=fixture();d["tables"]["visitas_comuns"].append({"comum":"BR-21-4444 - TESTE","cidade":"  itapevi  "})
        options,_=backup.locations(d["tables"])
        self.assertEqual({r["municipio"] for r in options},{"ITAPEVI"})

    def test_original_payload_resolves_city_even_when_group_has_no_city(self):
        d=fixture();d["tables"]["sam_gem_groups"].append({"id":"g2","congregacao":"PEDRAS (CHÁCARA SANTA MARIA)"})
        d["tables"]["sam_student_sync_state"].append({"id":"ss2","source_common":"PEDRAS (CHÁCARA SANTA MARIA)","source_payload":{"city":"Cotia"}})
        options,_,pending=backup.locations(d["tables"],include_pending=True)
        location=next(r for r in options if r["key"]=="PEDRAS (CHACARA SANTA MARIA)")
        self.assertEqual(location["municipio"],"COTIA");self.assertEqual(pending,[])

    def test_later_local_student_evidence_fills_existing_location(self):
        d=fixture();d["tables"]["sam_gem_groups"].append({"id":"g2","congregacao":"OUTRO NOME"})
        d["tables"]["musica_acompanhamento_aluno"].append({"id":"s2","comum_congregacao":"OUTRO NOME","municipio":"itapevi"})
        options,_=backup.locations(d["tables"])
        self.assertEqual(next(r for r in options if r["key"]=="OUTRO NOME")["municipio"],"ITAPEVI")

    def test_conflicting_source_cities_are_exposed_separately(self):
        d=fixture();d["tables"]["sam_student_sync_state"]=[{"source_common":"SEM CATÁLOGO","source_payload":{"city":"ITAPEVI"}}, {"source_common":"SEM CATÁLOGO","source_payload":{"city":"JANDIRA"}}]
        options,_,pending=backup.locations(d["tables"],include_pending=True)
        self.assertNotIn("SEM CATALOGO",{r["key"] for r in options})
        self.assertIn("SEM CATALOGO",{r["key"] for r in pending})

    def test_catalog_city_takes_precedence_over_source_variation(self):
        d=fixture();d["tables"]["sam_student_sync_state"].append({"source_common":"VILA DAS CHÁCARAS","source_payload":{"city":"JANDIRA"}})
        options,_=backup.locations(d["tables"])
        self.assertEqual(next(r for r in options if r["key"]=="BR-21-1111")["municipio"],"ITAPEVI")
