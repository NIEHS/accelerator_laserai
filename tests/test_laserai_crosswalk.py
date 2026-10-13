import json
import unittest
from pathlib import Path

from accelerator_core.utils.xcom_utils import DirectXcomPropsResolver
from accelerator_core.workflow.accel_data_models import IngestPayload, IngestSourceDescriptor
from accelerator_core.schema.templates.template_processor import AccelTemplateProcessor

from accelerator_laserai.hew_measures_crosswalk import HEWMeasuresTermMapper
from accelerator_laserai.laserai_crosswalk import LaserAIToHEWCrosswalk


class TestLaserAICrosswalk(unittest.TestCase):
    def test_hew_measures_mapper_matches_by_domain_and_preserves_unmapped_terms(self):
        mapper = HEWMeasuresTermMapper()

        self.assertEqual(
            "https://NIEHS.github.io/HEW_Measures/dist/Temperature",
            mapper("exposure", "temperature"),
        )
        self.assertEqual(
            "https://NIEHS.github.io/HEW_Measures/dist/Asthma",
            mapper("health_impact", "asthma"),
        )
        self.assertEqual(
            "https://NIEHS.github.io/HEW_Measures/dist/WomensHealth",
            mapper("health_impact", "Womens Health"),
        )
        self.assertEqual("Asthma", mapper("exposure", "Asthma"))
        self.assertEqual(
            "LaserAI-only term",
            mapper("health_impact", "LaserAI-only term"),
        )
        self.assertEqual(
            {
                "source_vocabularies": [
                    "https://NIEHS.github.io/HEW_Measures/hew_measures.jsonld"
                ],
                "exact_mappings": ["HP:0002099"],
            },
            mapper.annotation_metadata("health_impact", "Asthma"),
        )
        self.assertEqual(
            {},
            mapper.annotation_metadata("exposure", "LaserAI-only term"),
        )
        self.assertEqual(
            {
                "source_vocabularies": [
                    "https://NIEHS.github.io/HEW_Measures/hew_measures.jsonld"
                ],
                "aliases": ["Womens Health"],
                "exact_mappings": ["mesh:D016387"],
            },
            mapper.annotation_metadata("health_impact", "Womens Health"),
        )

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
        self.assertEqual("LiteratureResource", transformed["data"]["@type"])
        self.assertIn("submission", transformed)
        self.assertIn("technical_metadata", transformed)
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
                "asia",
            ],
            annotation["geography_annotations"][0]["geographic_locations"],
        )
        self.assertEqual(
            ["ocean_coastal"],
            annotation["geography_annotations"][0]["geographic_features"],
        )
        self.assertEqual(
            "Non-United States",
            annotation["geography_annotations"][0]["spatial_text"],
        )
        self.assertEqual(
            ["24500"],
            transformed["data"]["identifiers"],
        )
        self.assertEqual("research_article", transformed["data"]["publication_type"])
        self.assertEqual(
            [
                {
                    "id": "PERSON:laserai_orui",
                    "agent_type": "Person",
                    "family_name": "Orui",
                }
            ],
            transformed["data"]["authors"],
        )
        self.assertNotIn("agent_associations", transformed["data"])

    def test_translate_omits_authors_when_first_author_missing(self):
        crosswalk = LaserAIToHEWCrosswalk(
            DirectXcomPropsResolver(False, None),
            jsonld_serializer=lambda instance, class_name: instance,
        )
        for first_author in (None, "", "not reported", "---"):
            resource = crosswalk.translate_to_linkml(
                {
                    "source_reference_number": "1",
                    "bibliographic": {"title": "T", "first_author": first_author},
                }
            )
            self.assertNotIn("authors", resource)

    def test_translate_maps_year_to_publication_date(self):
        crosswalk = LaserAIToHEWCrosswalk(
            DirectXcomPropsResolver(False, None),
            jsonld_serializer=lambda instance, class_name: instance,
        )
        for year, expected in ((2024, "2024"), ("2024", "2024"), ("n.d.", None), (None, None)):
            resource = crosswalk.translate_to_linkml(
                {"source_reference_number": "1", "bibliographic": {"year": year}}
            )
            self.assertEqual(expected, resource.get("publication_date"))

    def test_translate_preserves_publication_subtitle(self):
        crosswalk = LaserAIToHEWCrosswalk(
            DirectXcomPropsResolver(False, None),
            jsonld_serializer=lambda instance, class_name: instance,
        )
        resource = crosswalk.translate_to_linkml(
            {
                "source_reference_number": "1",
                "bibliographic": {
                    "title": "Publication",
                    "subtitle": "A study subtitle",
                },
            }
        )
        self.assertEqual("A study subtitle", resource["subtitle"])


if __name__ == "__main__":
    unittest.main()
