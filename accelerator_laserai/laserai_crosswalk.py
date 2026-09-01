"""Crosswalk LaserAI intermediate records into the HEW LinkML shape."""

from __future__ import annotations

import re
from typing import Any, Callable

from accelerator_core.utils.xcom_utils import XcomPropsResolver
from accelerator_core.workflow.accel_source_ingest import IngestPayload
from accelerator_core.workflow.crosswalk import Crosswalk


TermMapper = Callable[[str, str], str]
JsonLdSerializer = Callable[..., dict[str, Any]]


def _without_not_reported(values: list[Any]) -> list[Any]:
    return [value for value in values if value and value != "not reported"]


def _flatten_levels(group: dict[str, Any], *legacy_keys: str) -> list[Any]:
    """Flatten the hierarchical intermediate shape, with legacy compatibility."""
    levels = group.get("levels")
    if isinstance(levels, dict):
        values = [value for level in levels.values() for value in level]
    else:
        values = [value for key in legacy_keys for value in group.get(key, [])]
    return values + group.get("write_in", [])


def _enum_value(value: str | None) -> str | None:
    """Convert the export's display labels to current HEW enum values."""
    if value is None or value == "not reported":
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return {
        "research_article": "research_article",
        "review_article": "review_article",
        "commentary_opinion": "commentary_opinion",
        "assessment_book_report": "assessment_book_report",
        "complete_resource": "complete_resource",
        "title_and_abstract_only": "abstract_and_title_only",
    }.get(normalized, normalized)


def _annotation_values(
    category: str,
    values: list[Any],
    map_term: TermMapper,
    *,
    parent_concept: str | None = None,
) -> list[dict[str, Any]]:
    annotations = []
    for value in _without_not_reported(values):
        annotation = {"coded_concept": map_term(category, str(value))}
        if parent_concept:
            annotation["parent_concept"] = parent_concept
        annotations.append(annotation)
    return annotations


def _level_annotations(
    category: str,
    group: dict[str, Any] | list[dict[str, Any]],
    map_term: TermMapper,
) -> list[dict[str, Any]]:
    """Map hierarchical terms while preserving their source coding depth."""
    if isinstance(group, list):
        annotations = []
        for rollup in group:
            for level in ("1", "2", "3"):
                value = rollup.get(f"level{level}")
                if value:
                    annotations.append(
                        {
                            "coded_concept": map_term(category, str(value)),
                            "coding_depth": int(level),
                        }
                    )
        return annotations

    annotations = []
    levels = group.get("levels", {})
    if isinstance(levels, dict):
        for level, values in levels.items():
            for value in _without_not_reported(values):
                annotations.append(
                    {
                        "coded_concept": map_term(category, str(value)),
                        "coding_depth": int(level),
                    }
                )
    else:
        annotations.extend(
            _annotation_values(
                category,
                _flatten_levels(group, "level_1", "level_2", "level_3"),
                map_term,
            )
        )

    for value in _without_not_reported(group.get("write_in", [])):
        annotations.append({"coded_concept": map_term(category, str(value))})
    return annotations


def _resource_id(reference_number: str) -> str:
    return f"HEWRES:laserai_{reference_number}"


class LaserAIToHEWCrosswalk(Crosswalk):
    """Convert one or more LaserAI intermediate records to HEW JSON."""

    def __init__(
        self,
        xcom_props_resolver: XcomPropsResolver,
        term_mapper: TermMapper | None = None,
        jsonld_serializer: JsonLdSerializer | None = None,
    ):
        super().__init__(xcom_props_resolver)
        self.term_mapper = term_mapper or (lambda _category, value: value)
        self.jsonld_serializer = jsonld_serializer or self._load_jsonld_serializer()

    @staticmethod
    def _load_jsonld_serializer() -> JsonLdSerializer:
        """Load the serializer from the reusable HEW model package."""
        try:
            from hew_model.jsonld import to_jsonld
        except ImportError as exc:
            raise ImportError(
                "The HEW model package is required for LaserAI JSON-LD output; "
                "install the accelerator_laserai requirements"
            ) from exc
        return to_jsonld

    def transform(self, ingest_result: IngestPayload) -> IngestPayload:
        """Resolve and crosswalk every intermediate LaserAI record."""
        output_payload = IngestPayload(ingest_result.ingest_source_descriptor)
        payload_length = self.get_payload_length(ingest_result)

        for index in range(payload_length):
            payload = self.payload_resolve(ingest_result, index)
            linkml_record = self.translate_to_linkml(payload)
            jsonld_record = self.jsonld_serializer(
                linkml_record,
                class_name="LiteratureResource",
            )
            self.report_individual(output_payload, linkml_record["id"], jsonld_record)

        output_payload.ingest_successful = True
        return output_payload

    def translate_to_linkml(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Build a best-effort HEW LiteratureResource JSON object."""
        reference_number = str(payload["source_reference_number"])
        resource_id = _resource_id(reference_number)
        bibliographic = payload.get("bibliographic", {})
        review = payload.get("review", {})

        resource: dict[str, Any] = {
            "id": resource_id,
            "title": bibliographic.get("title"),
            "resource_type": "literature",
            "doi": bibliographic.get("doi"),
            "identifiers": [reference_number],
            "annotations": [
                self._annotation(payload, resource_id, reference_number, review)
            ],
        }

        accession_number = bibliographic.get("accession_number")
        if accession_number is not None:
            accession = str(accession_number)
            if accession.isdigit():
                resource["pmid"] = accession
            else:
                resource["identifiers"].append(accession)

        first_author = bibliographic.get("first_author")
        if first_author:
            # HEW currently models authors as CURIEs. Keep a deterministic source
            # CURIE here until an author/person crosswalk is defined.
            author_slug = re.sub(r"[^a-z0-9]+", "_", str(first_author).lower()).strip("_")
            resource["authors"] = [f"HEW:laserai_author_{author_slug}"]

        return {key: value for key, value in resource.items() if value is not None}

    def _annotation(
        self,
        payload: dict[str, Any],
        resource_id: str,
        reference_number: str,
        review: dict[str, Any],
    ) -> dict[str, Any]:
        annotation: dict[str, Any] = {
            "id": f"HEWANN:laserai_{reference_number}",
            "subject": resource_id,
            "coding_scheme": "LaserAI Export",
            "coding_method": "laser_ai_generated",
        }

        reference_type = _enum_value(review.get("reference_type"))
        information_source = _enum_value(review.get("information_source"))
        if reference_type:
            annotation["reference_type"] = reference_type
        if information_source:
            annotation["information_source"] = information_source

        objectives = payload.get("study_objectives", [])
        if objectives:
            annotation["study_objective"] = objectives[0]

        exposures = payload.get("exposures", {})
        annotation["exposure_annotations"] = _level_annotations(
            "exposure", exposures, self.term_mapper
        )

        health_impacts = payload.get("health_impacts", {})
        annotation["health_impact_annotations"] = _level_annotations(
            "health_impact", health_impacts, self.term_mapper
        )

        geography = payload.get("geography", {})
        geography_annotation: dict[str, Any] = {}
        if isinstance(geography, list):
            locations = [
                value
                for rollup in geography
                for value in (rollup.get("level1"), rollup.get("level2"), rollup.get("level3"))
                if value and value != "not reported"
            ]
            features = _without_not_reported(
                payload.get("geographic_features", [])
            )
        else:
            locations_group = geography.get("locations", {})
            locations = _without_not_reported(
                _flatten_levels(locations_group, "locations_level_1", "locations_level_2")
            )
            if not locations_group:
                locations = _without_not_reported(
                    geography.get("locations_level_1", [])
                    + geography.get("locations_level_2", [])
                )
            features = _without_not_reported(geography.get("geographic_features", []))
        if locations:
            geography_annotation["geographic_locations"] = [
                self.term_mapper("geography", str(value)) for value in locations
            ]
        if features:
            geography_annotation["geographic_features"] = [
                self.term_mapper("geographic_feature", str(value)) for value in features
            ]
        annotation["geography_annotations"] = [geography_annotation] if geography_annotation else []

        data_and_models = payload.get("data_and_models", {})
        data_resource_types = data_and_models.get("data_resource_types", {})
        if not data_resource_types:
            data_resource_types = {
                "level_1": data_and_models.get("data_resource_types_level_1", []),
                "level_2": data_and_models.get("data_resource_types_level_2", []),
            }
        annotation["data_tool_method_annotations"] = [
            {
                "data_resource_types": [
                    self.term_mapper("data_resource_type", str(value))
                    for value in _without_not_reported(
                        _flatten_levels(data_resource_types, "level_1", "level_2")
                    )
                ],
                "model_types": [
                    self.term_mapper("model_type", str(value))
                    for value in _without_not_reported(data_and_models.get("model_types", []))
                ],
            }
        ]

        special_topics = payload.get("special_topics", {})
        annotation["special_topic_annotations"] = _level_annotations(
            "special_topic", special_topics, self.term_mapper
        )
        return annotation
