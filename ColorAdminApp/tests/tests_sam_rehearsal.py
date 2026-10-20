import copy
import json
import sqlite3
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve

from ColorAdminApp import sam_backup as backup, sam_backup_views as views, sam_rehearsal as rehearsal
from .tests_sam_backup import fixture


def source():
    document = fixture()
    document["tables"]["visitas_comuns"][0]["comum"] = "BR-22-2999 - VILA DAS CHÁCARAS"
    document["tables"]["musica_acompanhamento_msa"][0].update(
        paginas="1 - 21", licoes="1 - 4", clave="Sol", observacoes="Repassar — MSA em Grupo", autorizado_por=None)
    document["tables"]["musica_acompanhamento_metodo"] = [{"id":"method", "aluno_id":"s1", "data_inicio":"2025-05-01", "metodo":"Método original", "pagina":"09", "licao":"1 - 2", "autorizado_por":"Responsável original", "observacoes":"Preservar"}]
    document["tables"]["musica_acompanhamento_hinario"] = [{"id":"hymn", "aluno_id":"s1", "data":"2025-08-02", "hino":"110", "voz":"Voz Principal", "observacoes":"Hinário em Grupo", "autorizado_por":"Responsável original"}]
    document["tables"]["musica_acompanhamento_provas"] = [{"id":"exam", "aluno_id":"s1", "data_prova":"2025-06-01", "modulo":"Módulo 1", "nota":0, "observacoes":"Nota zero não pode sumir"}]
    document["tables"]["musica_acompanhamento_escala"] = [{"id":"scale", "aluno_id":"s1", "data":"2025-07-01", "escala":"Dó maior"}]
    document["tables"]["musica_acompanhamento_atividades"] = [{"id":"activity", "aluno_id":"s1", "data_atividade":"2025-08-01", "titulo":"Marco", "tipo_atividade":"documento", "documento_url":"https://example.invalid/document"}]
    return backup.seal(document)


class RehearsalTests(SimpleTestCase):
    def test_only_correct_common_and_city_are_accepted(self):
        with self.assertRaises(backup.BackupError):rehearsal.build(backup.seal(fixture()),"g1")
        document=source();document["tables"]["visitas_comuns"][0]["cidade"]="JANDIRA"
        with self.assertRaises(backup.BackupError):rehearsal.build(backup.seal(document),"g1")
        with self.assertRaises(backup.BackupError):rehearsal.build(source(),"other-group")

    def test_unsealed_or_modified_backup_is_refused(self):
        document=source();document["tables"]["sam_gem_groups"][0]["turma"]="ALTERADA"
        with self.assertRaises(backup.BackupError):rehearsal.build(document,"g1")

    def test_fields_dates_nulls_and_group_markers_survive_roundtrip(self):
        document=source();original=copy.deepcopy(document)
        with TemporaryDirectory() as directory,override_settings(SAM_BACKUP_DIR=directory):
            result=rehearsal.create(document,"g1");report=rehearsal.read(result["id"])
            for kind,(table,_) in rehearsal.SOURCE_CONFIG.items():
                received={key:value for key,value in report["history"][kind][0].items() if key!="sandbox_id"}
                self.assertEqual(received,document["tables"][table][0])
            self.assertIsNone(report["history"]["msa"][0]["autorizado_por"])
            self.assertEqual(report["history"]["provas"][0]["nota"],0)
            self.assertFalse(report["groups"][0]["classes"][0]["attendance"][0]["presente"])
            self.assertEqual(report["location"]["key"],"BR-22-2999")
            self.assertEqual(report["location"]["municipio"],"ITAPEVI")
            self.assertTrue(all(report["verification"].values()))
        self.assertEqual(document,original)

    def test_retry_is_idempotent_and_ids_are_stable(self):
        with TemporaryDirectory() as directory,override_settings(SAM_BACKUP_DIR=directory):
            document=source();first=rehearsal.create(document,"g1");before=rehearsal.read(first["id"])
            second=rehearsal.create(document,"g1");after=rehearsal.read(second["id"])
            self.assertEqual(first["id"],second["id"]);self.assertTrue(second["reused"])
            self.assertEqual(before,after)
            self.assertEqual(len(rehearsal.list_runs()),1)
            self.assertEqual(after["summary"]["history"],6)

    def test_history_is_linked_to_student_not_invented_class_relation(self):
        spec=rehearsal.build(source(),"g1")
        links=[r for r in spec["relations"] if r["kind"] in rehearsal.SOURCE_CONFIG]
        self.assertEqual({r["relation"] for r in links},{"student"})
        self.assertEqual(len(links),6)

    def test_missing_profile_keeps_member_without_inventing_history(self):
        document=source();document["tables"]["musica_acompanhamento_aluno"]=[]
        document=backup.seal(document);spec=rehearsal.build(document,"g1")
        self.assertEqual(spec["manifest"]["counts"]["students"],1)
        self.assertEqual(sum(spec["manifest"]["history_counts"].values()),0)
        self.assertIn("missing_profile",{r["code"] for r in spec["manifest"]["issues"]})

    def test_conflicting_identity_does_not_attach_another_students_records(self):
        document=source();document["tables"]["sam_student_sync_state"][0]["aluno_id"]="s2"
        spec=rehearsal.build(backup.seal(document),"g1")
        self.assertEqual(sum(spec["manifest"]["history_counts"].values()),0)
        self.assertIn("ambiguous_identity",{r["code"] for r in spec["manifest"]["issues"]})

    def test_no_network_is_used_during_creation_read_or_retry(self):
        with TemporaryDirectory() as directory,override_settings(SAM_BACKUP_DIR=directory):
            with patch("requests.get",side_effect=AssertionError("No network")),patch("requests.post",side_effect=AssertionError("No network")),patch("requests.patch",side_effect=AssertionError("No network")),patch("requests.put",side_effect=AssertionError("No network")),patch("requests.delete",side_effect=AssertionError("No network")):
                document=source();run=rehearsal.create(document,"g1");rehearsal.read(run["id"])
                self.assertTrue(rehearsal.create(document,"g1")["reused"])
                self.assertEqual(len(rehearsal.list_runs()),1)

    def test_failure_rolls_back_entire_run(self):
        with TemporaryDirectory() as directory,override_settings(SAM_BACKUP_DIR=directory):
            with patch("ColorAdminApp.sam_rehearsal._verify",side_effect=backup.BackupError("Forced failure")):
                with self.assertRaises(backup.BackupError):rehearsal.create(source(),"g1")
            self.assertEqual(rehearsal.list_runs(),[])

    def test_modified_rehearsal_is_refused(self):
        with TemporaryDirectory() as directory,override_settings(SAM_BACKUP_DIR=directory):
            run=rehearsal.create(source(),"g1")
            connection=sqlite3.connect(rehearsal._path())
            connection.execute("UPDATE entities SET payload='{}' WHERE kind='msa'");connection.commit();connection.close()
            with self.assertRaises(backup.BackupError):rehearsal.read(run["id"])

    def test_sqlite_enforces_foreign_keys_for_test_entities(self):
        with TemporaryDirectory() as directory,override_settings(SAM_BACKUP_DIR=directory):
            run=rehearsal.create(source(),"g1");connection=rehearsal._connect(write=True)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO relations VALUES (?,?,?,?,?)",(run["id"],"msa","h1","invalid","missing-target"))
            connection.rollback();connection.close()


class RehearsalViewTests(SimpleTestCase):
    def request(self,payload,role=1):
        request=RequestFactory().post("/gem/sam/backup/ensaios/",json.dumps(payload),content_type="application/json")
        request.session={"authenticated":True,"user_profile":{"role_id":role},"user_id":"owner"}
        return request

    @patch("ColorAdminApp.sam_backup_views.sam_backup.load")
    def test_non_owner_and_wrong_location_are_refused_before_loading(self,load):
        payload={"backup_id":"id","group_id":"g1","comum":"BR-22-2999"}
        self.assertEqual(views.rehearsals(self.request(payload,role=2)).status_code,403)
        payload["comum"]="BR-21-1111"
        self.assertEqual(views.rehearsals(self.request(payload)).status_code,400)
        load.assert_not_called()

    @patch("ColorAdminApp.sam_backup_views.sam_backup.load")
    def test_missing_snapshot_is_refused(self,load):
        self.assertEqual(views.rehearsals(self.request({"group_id":"g1","comum":"BR-22-2999"})).status_code,400)
        load.assert_not_called()

    def test_real_local_endpoint_roundtrip(self):
        with TemporaryDirectory() as directory,override_settings(SAM_BACKUP_DIR=directory):
            document=backup.save(source())
            payload={"backup_id":document["id"],"group_id":"g1","comum":"BR-22-2999"}
            response=views.rehearsals(self.request(payload));self.assertEqual(response.status_code,201)
            second=views.rehearsals(self.request(payload));self.assertEqual(second.status_code,200)
            result=json.loads(response.content)
            request=RequestFactory().get("/gem/sam/backup/ensaios/");request.session=self.request(payload).session
            response=views.rehearsal_detail(request,result["id"])
            self.assertEqual(response.status_code,200)
            self.assertFalse(json.loads(response.content)["sam_write_enabled"])
            self.assertEqual(resolve(f"/gem/sam/backup/ensaios/{result['id']}/").url_name,"samBackupRehearsalDetail")
