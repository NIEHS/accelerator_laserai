import json
import unittest
from pathlib import Path

from accelerator_core.utils.xcom_utils import DirectXcomPropsResolver
from accelerator_core.workflow.accel_data_models import IngestPayload, IngestSourceDescriptor

from accelerator_laserai.laserai_crosswalk import LaserAIToHEWCrosswalk


class TestLaserAICrosswalk(unittest.TestCase):
    def test_crosswalks_intermediate_record_to_hew_shape(self):
        record_path = (
            Path(__file__).parent.parent
            / "integration_tests"
            / "test_resources"
            / "f7abc5b7-1fb0-4941-9347-57a724c103f0.json"
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
        self.assertEqual("HEWRES:laserai_3541", transformed["id"])
        self.assertEqual("literature", transformed["resource_type"])
        self.assertEqual("38639787", transformed["pmid"])
        self.assertEqual(
            "TEST:exposure:Temperature",
            transformed["annotations"][0]["exposure_annotations"][0]["coded_concept"],
        )


if __name__ == "__main__":
    unittest.main()
