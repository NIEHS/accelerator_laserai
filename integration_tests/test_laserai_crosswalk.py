import json
import unittest
from pathlib import Path

from accelerator_core.schema.templates.template_processor import AccelTemplateProcessor
from accelerator_core.utils.xcom_utils import DirectXcomPropsResolver
from accelerator_core.workflow.accel_data_models import IngestPayload, IngestSourceDescriptor

from accelerator_laserai.laserai_crosswalk import LaserAIToHEWCrosswalk


class TestLaserAICrosswalkIntegration(unittest.TestCase):
    TEST_RESOURCES_DIR = Path(__file__).parent / "test_resources"
    INPUT_PATH = (
        TEST_RESOURCES_DIR
        / "test_laser1.json"
    )
    OUTPUT_DIR = TEST_RESOURCES_DIR / "temp_dirs/jsonld"

    def test_crosswalk_publishes_jsonld_document(self):
        if not self.INPUT_PATH.exists():
            self.skipTest("LaserAI intermediate JSON fixture is not present")

        with self.INPUT_PATH.open(encoding="utf-8") as input_file:
            record = json.load(input_file)
        record = AccelTemplateProcessor().render_generic(
            record,
            {"submitter_name": "", "submitter_email": "", "submitter_comment": ""},
            {
                "original_source_identifier": record["bibliographic"]["doi"],
                "original_source_link": "laserai.xlsx",
                "history": [],
            },
        )

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

        self.assertEqual("LiteratureResource", jsonld["data"]["@type"])
        self.assertEqual("HEWRES:laserai_25505", jsonld["data"]["id"])
        self.assertIn("WOS:001260496000001", jsonld["data"]["identifiers"])
        self.assertEqual(
            [
                {"name": "Non-United States", "location_type": "other"},
                {"name": "Asia", "location_type": "other"},
            ],
            jsonld["data"]["annotations"][0]["geography_annotations"][0]["locations"],
        )
        self.assertIn("submission", jsonld)
        self.assertIn("technical_metadata", jsonld)


if __name__ == "__main__":
    unittest.main()
