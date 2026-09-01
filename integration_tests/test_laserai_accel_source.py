import json
import unittest
from pathlib import Path

from accelerator_core.utils.xcom_utils import DirectXcomPropsResolver
from accelerator_core.workflow.accel_data_models import IngestSourceDescriptor

from accelerator_laserai.laserai_accel_source import LaserAIAccelSource


class TestLaserAIAccelSourceIntegration(unittest.TestCase):
    TEST_RESOURCES_DIR = Path(__file__).parent / "test_resources"
    INPUT_PATH = TEST_RESOURCES_DIR / "LaserAI Export.xlsx"
    OUTPUT_DIR = TEST_RESOURCES_DIR / "temp_dirs"

    def test_ingest_writes_one_json_file_per_reference(self):
        if not self.INPUT_PATH.exists():
            self.skipTest(
                "Private LaserAI workbook is not present in integration_tests/test_resources"
            )

        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for output_path in self.OUTPUT_DIR.glob("*.json"):
            output_path.unlink()

        descriptor = IngestSourceDescriptor()
        descriptor.ingest_identifier = "laserai-integration-test"
        descriptor.ingest_item_id = "laserai"
        descriptor.use_tempfiles = True

        source = LaserAIAccelSource(
            descriptor,
            DirectXcomPropsResolver(
                temp_files_supported=True,
                temp_files_location=str(self.OUTPUT_DIR),
            ),
        )

        payload = source.ingest_single(str(self.INPUT_PATH), {})

        self.assertTrue(payload.ingest_successful)
        self.assertFalse(payload.payload_inline)
        self.assertEqual(2518, len(payload.payload_path))

        output_paths = [Path(path) for path in payload.payload_path]
        self.assertTrue(all(path.parent == self.OUTPUT_DIR for path in output_paths))
        self.assertEqual(2518, len(list(self.OUTPUT_DIR.glob("*.json"))))

        with output_paths[0].open(encoding="utf-8") as output_file:
            first_record = json.load(output_file)

        self.assertEqual("22", first_record["source_reference_number"])
        self.assertEqual(
            "10.1007/s00345-024-05119-6",
            first_record["bibliographic"]["doi"],
        )
        for category in ("exposures", "health_impacts", "geography"):
            self.assertIsInstance(first_record[category], list)
            for rollup in first_record[category]:
                self.assertEqual(
                    {"level1", "level2", "level3"}, rollup.keys()
                )


if __name__ == "__main__":
    unittest.main()
