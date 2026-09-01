import json
import unittest
from pathlib import Path

from accelerator_core.utils.xcom_utils import DirectXcomPropsResolver
from accelerator_core.workflow.accel_data_models import IngestPayload, IngestSourceDescriptor

from accelerator_laserai.laserai_crosswalk import LaserAIToHEWCrosswalk


class TestLaserAICrosswalkIntegration(unittest.TestCase):
    TEST_RESOURCES_DIR = Path(__file__).parent / "test_resources"
    INPUT_PATH = (
        TEST_RESOURCES_DIR
        / "f7abc5b7-1fb0-4941-9347-57a724c103f0.json"
    )
    OUTPUT_DIR = TEST_RESOURCES_DIR / "temp_dirs/jsonld"

    def test_crosswalk_publishes_jsonld_document(self):
        if not self.INPUT_PATH.exists():
            self.skipTest("LaserAI intermediate JSON fixture is not present")

        with self.INPUT_PATH.open(encoding="utf-8") as input_file:
            record = json.load(input_file)

        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        descriptor = IngestSourceDescriptor()
        descriptor.ingest_identifier = "laserai-crosswalk-integration-test"
        descriptor.ingest_item_id = "laserai"
        descriptor.use_tempfiles = True

        ingest_payload = IngestPayload(descriptor)
        ingest_payload.payload.append(record)

        crosswalk = LaserAIToHEWCrosswalk(
            DirectXcomPropsResolver(
                temp_files_supported=True,
                temp_files_location=str(self.OUTPUT_DIR),
            )
        )
        result = crosswalk.transform(ingest_payload)

        self.assertTrue(result.ingest_successful)
        self.assertFalse(result.payload_inline)
        self.assertEqual(1, len(result.payload_path))

        output_path = Path(result.payload_path[0])
        self.assertEqual(self.OUTPUT_DIR, output_path.parent)
        self.assertTrue(output_path.exists())
        with output_path.open(encoding="utf-8") as output_file:
            jsonld = json.load(output_file)

        self.assertEqual("LiteratureResource", jsonld["@type"])
        self.assertEqual("HEWRES:laserai_3541", jsonld["id"])
        self.assertEqual("38639787", jsonld["pmid"])


if __name__ == "__main__":
    unittest.main()
