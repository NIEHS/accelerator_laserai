import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile

from openpyxl import Workbook

from accelerator_core.utils.xcom_utils import DirectXcomPropsResolver
from accelerator_core.workflow.accel_data_models import IngestSourceDescriptor

from accelerator_laserai.laserai_accel_source import LaserAIAccelSource


class TestLaserAIAccelSource(unittest.TestCase):
    def source(self):
        descriptor = IngestSourceDescriptor()
        descriptor.ingest_identifier = "laserai-test-run"
        descriptor.ingest_item_id = "laserai"
        descriptor.use_tempfiles = False
        return LaserAIAccelSource(
            descriptor,
            DirectXcomPropsResolver(temp_files_supported=False, temp_files_location=None),
        )

    def test_groups_rows_by_reference_number(self):
        with NamedTemporaryFile(suffix=".xlsx") as temporary:
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.append(
                [
                    "1st Author",
                    "Year",
                    "Title",
                    "Reference number",
                    "DOI",
                    "Exposure L1 (extracted)",
                    "Exposure L2 (extracted)",
                ]
            )
            worksheet.append(["Author", 2024, "Title", 22, "10/example", "Temperature"])
            worksheet.append(["Author", 2024, "Title", 22, "10/example", "Humidity"])
            worksheet.append(["Author", 2024, "Title", 22, "10/example", None, "Heatwave"])
            worksheet.append(["Other", 2024, "Other title", 23, "10/other", "Flood"])
            workbook.save(temporary.name)
            workbook.close()

            records = LaserAIAccelSource.parse_workbook(temporary.name)

        self.assertEqual(
            ["22", "23"],
            [record["source_reference_number"] for record in records],
        )
        self.assertEqual(
            [
                {"level1": "Temperature", "level2": "", "level3": ""},
                {"level1": "Humidity", "level2": "", "level3": ""},
                {"level1": "", "level2": "Heatwave", "level3": ""},
            ],
            records[0]["exposures"],
        )
        self.assertEqual(
            [], records[0]["health_impacts"]
        )
        self.assertEqual(
            [{"level1": "Flood", "level2": "", "level3": ""}],
            records[1]["exposures"],
        )
        self.assertEqual(
            ["Temperature", "Humidity", "Heatwave"],
            records[0]["raw_values"]["Exposure L1 (extracted)"]
            + records[0]["raw_values"].get("Exposure L2 (extracted)", []),
        )

    def test_ingest_emits_one_payload_per_reference(self):
        workbook_path = Path(__file__).parent / "test_resources" / "LaserAI Export.xlsx"
        if not workbook_path.exists():
            self.skipTest("Private LaserAI workbook is not present")

        source = self.source()
        descriptor = source.ingest_source_descriptor
        payload = source.ingest_single(str(workbook_path), {})

        self.assertTrue(payload.ingest_successful)
        self.assertEqual(2518, len(payload.payload))
        self.assertEqual("22", payload.payload[0]["source_reference_number"])
        self.assertEqual(
            "10.1007/s00345-024-05119-6",
            payload.payload[0]["bibliographic"]["doi"],
        )
        self.assertEqual("laserai-test-run", descriptor.ingest_identifier)


if __name__ == "__main__":
    unittest.main()
