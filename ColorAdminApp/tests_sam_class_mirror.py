from django.test import SimpleTestCase

from .sam_class_mirror import parse_attendance, parse_class_detail, parse_class_row


class SamClassMirrorTests(SimpleTestCase):
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
