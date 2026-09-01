import json
import unittest
from pathlib import Path

from accelerator_core.utils.xcom_utils import DirectXcomPropsResolver
from accelerator_core.workflow.accel_data_models import IngestPayload, IngestSourceDescriptor

from accelerator_laserai.laserai_crosswalk import LaserAIToHEWCrosswalk


class TestLaserAICrosswalk(unittest.TestCase):
    def test_crosswalks_intermediate_record_to_hew_shape(self):
        record_path = (
            Path(__file__).parent
            / "test_resources"
            / "0a0cb18d-7a31-445b-9dec-fcf088d4cd0e.json"
        )
        if not record_path.exists():
            self.skipTest("LaserAI intermediate JSON fixture is not present")

        with record_path.open(encoding="utf-8") as record_file:
            record = json.load(record_file)

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
        self.assertEqual("LiteratureResource", transformed["@type"])
        self.assertEqual("https://example.org/test-context", transformed["@context"])
        self.assertEqual("HEWRES:laserai_4451", transformed["id"])
        self.assertEqual("literature", transformed["resource_type"])
        self.assertEqual("38270762", transformed["pmid"])
        annotation = transformed["annotations"][0]
        self.assertEqual(
            [
                {
                    "coded_concept": "TEST:exposure:Temperature",
                    "coding_depth": 1,
                },
                {
                    "coded_concept": "TEST:exposure:Extreme Heat/Heat",
                    "coding_depth": 2,
                },
                {
                    "coded_concept": "TEST:exposure:Air Pollution",
                    "coding_depth": 1,
                },
            ],
            annotation["exposure_annotations"],
        )
        self.assertEqual(
            [
                {
                    "coded_concept": "TEST:health_impact:Morbidity/Mortality",
                    "coding_depth": 1,
                }
            ],
            annotation["health_impact_annotations"],
        )
        self.assertEqual(
            [
                "TEST:geography:Non-United States",
                "TEST:geography:Non-U.S. North America",
            ],
            annotation["geography_annotations"][0]["geographic_locations"],
        )
        self.assertEqual(
            ["TEST:geographic_feature:Urban"],
            annotation["geography_annotations"][0]["geographic_features"],
        )


if __name__ == "__main__":
    unittest.main()
