import json
import unittest
from pathlib import Path

from accelerator_core.utils.xcom_utils import DirectXcomPropsResolver
from accelerator_core.workflow.accel_data_models import IngestPayload, IngestSourceDescriptor
from accelerator_core.schema.templates.template_processor import AccelTemplateProcessor

from accelerator_laserai.laserai_crosswalk import LaserAIToHEWCrosswalk


class TestLaserAICrosswalk(unittest.TestCase):
    def test_crosswalks_intermediate_record_to_hew_shape(self):
        record_path = (
            Path(__file__).parent
            / "test_resources"
            / "laserai_crosswalk.json"
        )
        if not record_path.exists():
            self.skipTest("LaserAI intermediate JSON fixture is not present")

        with record_path.open(encoding="utf-8") as record_file:
            record = json.load(record_file)
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
        descriptor.ingest_identifier = "laserai-crosswalk-test"
        descriptor.ingest_item_id = "laserai"
        ingest_payload = IngestPayload(descriptor)
        ingest_payload.payload.append(record)

        crosswalk = LaserAIToHEWCrosswalk(
            DirectXcomPropsResolver(False, None),
            term_mapper=lambda category, value: f"TEST:{category}:{value}",
            jsonld_serializer=lambda instance, class_name: {
                "@context": "https://example.org/test-context",
                "@type": class_name,
                **instance,
            },
        )
        result = crosswalk.transform(ingest_payload)

        self.assertEqual(1, len(result.payload))
        transformed = result.payload[0]
        self.assertEqual("LiteratureResource", transformed["data"]["@type"])
        self.assertEqual("https://example.org/test-context", transformed["data"]["@context"])
        self.assertEqual("HEWRES:laserai_24500", transformed["data"]["id"])
        self.assertEqual("literature", transformed["data"]["resource_type"])
        self.assertEqual("39497795", transformed["data"]["pmid"])
        annotation = transformed["data"]["annotations"][0]
        self.assertEqual(
            [
                {
                    "coded_concept": "TEST:exposure:Extreme Weather-Related Event or Disaster",
                    "coding_depth": 1,
                },
                {
                    "coded_concept": "TEST:exposure:Earthquake",
                    "coding_depth": 2,
                },
                {
                    "coded_concept": "TEST:exposure:Extreme Weather-Related Event or Disaster",
                    "coding_depth": 1,
                },
                {
                    "coded_concept": "TEST:exposure:Tsunami",
                    "coding_depth": 2,
                },
            ],
            annotation["exposure_annotations"],
        )
        self.assertEqual(
            [
                {
                    "coded_concept": "TEST:health_impact:Mental Health and Well-Being",
                    "coding_depth": 1,
                },
                {
                    "coded_concept": "TEST:health_impact:Mood Disorder",
                    "coding_depth": 2,
                },
                {
                    "coded_concept": "TEST:health_impact:Mental Health and Well-Being",
                    "coding_depth": 1,
                },
                {
                    "coded_concept": "TEST:health_impact:Suicide Ideation",
                    "coding_depth": 2,
                },
            ],
            annotation["health_impact_annotations"],
        )
        self.assertEqual(
            [
                "TEST:geography:Non-United States",
                "TEST:geography:Asia",
            ],
            annotation["geography_annotations"][0]["geographic_locations"],
        )
        self.assertEqual(
            ["TEST:geographic_feature:Ocean/Coastal"],
            annotation["geography_annotations"][0]["geographic_features"],
        )
        self.assertEqual(
            [
                {"name": "Non-United States", "location_type": "other"},
                {"name": "Asia", "location_type": "other"},
            ],
            annotation["geography_annotations"][0]["locations"],
        )
        self.assertIn("submission", transformed)
        self.assertIn("technical_metadata", transformed)


if __name__ == "__main__":
    unittest.main()
