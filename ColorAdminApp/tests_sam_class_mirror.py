from pathlib import Path

from django.test import SimpleTestCase

from .sam_class_mirror import parse_attendance, parse_class_detail, parse_class_row, parse_group_row


class SamClassMirrorTests(SimpleTestCase):
    def test_group_row_extracts_schedule_period_and_status(self):
        row = parse_group_row([
            '<input type="radio" value="63351">', "ÁGUA ESPRAIADA", "TEORIA MUSICAL",
            "TEORIA MUSICAL FUNDAMENTAL", '<span>8</span>', "30/01/2026", "18/12/2026",
            "SEX - 19:30 ÀS 21:00", '<i class="fa fa-check"></i>', '<button onclick="editarTurma(63351)">Editar</button>',
        ])

        self.assertEqual(row["source_id"], "63351")
        self.assertEqual(row["matriculados"], 8)
        self.assertEqual(row["data_inicio"], "2026-01-30")
        self.assertEqual(row["data_termino"], "2026-12-18")
        self.assertEqual(row["dia_horario"], "SEX - 19:30 ÀS 21:00")
        self.assertTrue(row["ativo"])
    def test_class_row_preserves_stable_ids(self):
        row = parse_class_row([
            "452766", "JARDIM PAULISTA - ITAPEVI", "TEORIA MUSICAL", "INSTRUMENTOS DE SOPRO", "27-08-2026",
            '<button onclick="visualizarFrequencias(452766, 63351)">Frequência</button>', "", "",
        ])
        self.assertEqual(row["source_id"], "452766")
        self.assertEqual(row["turma_source_id"], "63351")
        self.assertEqual(row["data_aula"], "2026-08-27")

    def test_attendance_distinguishes_present_and_absent(self):
        document = """
        <table><tbody>
          <tr><td>ALUNO PRESENTE</td><td><a data-id-membro="862995" data-id-freq="1953910"><i class="fa fa-check text-success"></i></a></td></tr>
          <tr><td>ALUNO AUSENTE</td><td><a data-id-membro="862996" data-id-freq=""><i class="fa fa-remove text-danger"></i></a></td></tr>
        </tbody></table>
        """
        rows = parse_attendance(document)
        self.assertTrue(rows[0]["presente"])
        self.assertFalse(rows[1]["presente"])
        self.assertEqual(rows[0]["source_member_id"], "862995")

    def test_attendance_sanitizes_invalid_bigint_attributes(self):
        document = """
        <table><tbody>
          <tr><td>SEM MEMBRO</td><td><a data-id-membro='""' data-id-freq='""'><i class="fa fa-remove text-danger"></i></a></td></tr>
          <tr><td>MEMBRO VÁLIDO</td><td><a data-id-membro="id: 862997" data-id-freq='""'><i class="fa fa-check text-success"></i></a></td></tr>
        </tbody></table>
        """
        rows = parse_attendance(document)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_member_id"], "862997")
        self.assertIsNone(rows[0]["source_frequency_id"])
    def test_class_detail_extracts_instructors_and_times(self):
        document = """
        <h4>Detalhes da Aula <span>27/08/2026</span></h4><table><tbody>
          <tr><td><strong>Início</strong></td><td>19:00:00</td></tr>
          <tr><td><strong>Término</strong></td><td>21:30:00</td></tr>
          <tr><td><strong>Instrutor(a) responsável</strong></td><td>RESPONSÁVEL</td></tr>
          <tr><td><strong>Instrutor(a) que ministrou a aula</strong></td><td>INSTRUTOR</td></tr>
        </tbody></table>
        """
        detail = parse_class_detail(document)
        self.assertEqual(detail["data_aula"], "2026-08-27")
        self.assertEqual(detail["inicio"], "19:00:00")
        self.assertEqual(detail["instrutor_aula"], "INSTRUTOR")

    def test_schema_models_group_enrollment_and_student_evolution(self):
        migration = Path(__file__).parent.parent / "scripts" / "migrations" / "024_sam_gem_groups_student_evolution.sql"
        sql = migration.read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.sam_gem_groups", sql)
        self.assertIn("create table if not exists public.sam_gem_enrollments", sql)
        self.assertIn("create or replace view public.sam_gem_student_evolution", sql)
        self.assertIn("Reorganiza imediatamente o acervo já importado", sql)
        self.assertIn("on conflict (turma_id, source_member_id) do update", sql)
        self.assertIn("'FREQUENCIA'", sql)
        self.assertIn("'NIVEL'", sql)

    def test_class_sync_links_group_class_enrollment_and_student(self):
        command = Path(__file__).parent / "management" / "commands" / "sync_sam_classes.py"
        content = command.read_text(encoding="utf-8")

        self.assertIn('self._upsert("sam_gem_groups"', content)
        self.assertIn('"turma_id": saved_group["id"]', content)
        self.assertIn('self._upsert("sam_gem_enrollments"', content)
        self.assertIn('source_state.get("aluno_id")', content)
