import json
import tempfile
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

        descriptor = IngestSourceDescriptor()
        descriptor.ingest_identifier = "laserai-crosswalk-integration-test"
        descriptor.ingest_item_id = "laserai"
        descriptor.use_tempfiles = True

        ingest_payload = IngestPayload(descriptor)
        ingest_payload.payload.append(record)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            crosswalk = LaserAIToHEWCrosswalk(
                DirectXcomPropsResolver(
                    temp_files_supported=True,
                    temp_files_location=str(output_dir),
                )
            )
            result = crosswalk.transform(ingest_payload)

            self.assertTrue(result.ingest_successful)
            self.assertFalse(result.payload_inline)
            self.assertEqual(1, len(result.payload_path))

            output_path = Path(result.payload_path[0])
            self.assertEqual(output_dir, output_path.parent)
            self.assertTrue(output_path.exists())
            with output_path.open(encoding="utf-8") as output_file:
                jsonld = json.load(output_file)

            self.assertEqual("LiteratureResource", jsonld["data"]["@type"])
            self.assertIsInstance(jsonld["data"]["@context"], dict)
            self.assertEqual(
                "https://w3id.org/hew/",
                jsonld["data"]["@context"]["@vocab"],
            )
            self.assertEqual("HEWRES:laserai_8689", jsonld["data"]["id"])
            self.assertEqual("38959513", jsonld["data"]["pmid"])
            self.assertEqual(
                "Knowledge Is Power: Protect Older Adults Against High and Sustained Heat Events",
                jsonld["data"]["title"],
            )
            self.assertEqual(
                "10.3928/00989134-20240618-01",
                jsonld["data"]["doi"],
            )
            self.assertEqual(
                [
                    {
                        "@type": "Person",
                        "id": "PERSON:laserai_husser",
                        "agent_type": "Person",
                        "family_name": "Husser",
                    }
                ],
                jsonld["data"]["authors"],
            )
            self.assertEqual("commentary_opinion", jsonld["data"]["publication_type"])
            self.assertEqual("2024", jsonld["data"]["publication_date"])
            self.assertIn("PERSON", jsonld["data"]["@context"])
            self.assertEqual(
                ["8689"],
                jsonld["data"]["identifiers"],
            )
            annotation = jsonld["data"]["annotations"][0]
            self.assertEqual("HEWANN:laserai_8689", annotation["id"])
            self.assertEqual("commentary_opinion", annotation["reference_type"])
            self.assertEqual("complete_resource", annotation["information_source"])
            geography_annotation = annotation["geography_annotations"][0]
            self.assertEqual(
                ["global_or_unspecified_location"],
                geography_annotation["geographic_locations"],
            )
            self.assertNotIn("spatial_text", geography_annotation)
            self.assertIn("submission", jsonld)
            self.assertIn("technical_metadata", jsonld)


if __name__ == "__main__":
    unittest.main()
