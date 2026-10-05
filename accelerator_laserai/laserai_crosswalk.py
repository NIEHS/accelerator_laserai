"""Crosswalk LaserAI intermediate records into the HEW LinkML shape."""

from __future__ import annotations

import re
from functools import partial
from pathlib import Path
from typing import Any, Callable

from accelerator_core.schema.templates.template_processor import AccelTemplateProcessor
from accelerator_core.utils.xcom_utils import XcomPropsResolver
from accelerator_core.workflow.accel_source_ingest import IngestPayload
from accelerator_core.workflow.crosswalk import Crosswalk


TermMapper = Callable[[str, str], str]
JsonLdSerializer = Callable[..., dict[str, Any]]

_REFERENCE_TYPES = {
    "research_article",
    "review_article",
    "commentary_opinion",
    "assessment_book_report",
}
_INFORMATION_SOURCES = {"complete_resource", "abstract_and_title_only"}
_GEOGRAPHIC_LOCATIONS = {
    "global_or_unspecified_location",
    "africa",
    "antarctica",
    "asia",
    "australasia",
    "central_south_america",
    "europe",
    "non_us_north_america",
    "united_states",
}
_GEOGRAPHIC_FEATURES = {
    "general_geographic_feature",
    "built_environment",
    "desert",
    "forest",
    "freshwater",
    "grassland",
    "island",
    "mountain",
    "ocean_coastal",
    "polar",
    "rainforest",
    "rural",
    "temperate",
    "tropical",
    "urban",
    "valley",
    "wetland",
    "other",
}
_DATA_RESOURCE_TYPES = {
    "cohort",
    "source_cohort_publication",
    "dataset",
    "software_code_library",
    "survey",
    "other",
}
_MODEL_TYPES = {
    "artificial_intelligence_machine_learning",
    "exposure_modeling",
    "geospatial_modeling",
    "other",
}


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


def _enum_value(value: str | None, allowed: set[str]) -> str | None:
    """Convert a display label to a normalized value without inventing enums."""
    if value is None or value == "not reported":
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    candidate = {
        "research_article": "research_article",
        "review_article": "review_article",
        "commentary_opinion": "commentary_opinion",
        "assessment_book_report": "assessment_book_report",
        "complete_resource": "complete_resource",
        "title_and_abstract_only": "abstract_and_title_only",
    }.get(normalized)
    return candidate if candidate in allowed else None


def _closed_enum_values(
    values: list[Any],
    allowed: set[str],
    aliases: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """Return valid enum members and source labels that need text preservation."""
    mapped = []
    unmapped = []
    aliases = aliases or {}
    for value in _without_not_reported(values):
        normalized = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
        candidate = aliases.get(normalized, normalized)
        if candidate in allowed:
            if candidate not in mapped:
                mapped.append(candidate)
        else:
            unmapped.append(str(value))
    return mapped, unmapped


def _unique_strings(values: list[Any]) -> list[str]:
    result = []
    for value in values:
        if value is None:
            continue
        value = str(value)
        if value and value not in result:
            result.append(value)
    return result


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


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def _authors(first_author: Any) -> list[dict[str, Any]]:
    """Map the LaserAI first author to an inlined HEW 2.0 Person.

    LaserAI exports only the first author's surname, so the Person carries
    ``family_name`` alone.
    """
    if not first_author or first_author == "not reported":
        return []
    author_slug = _slug(first_author)
    if not author_slug:
        return []
    return [
        {
            "id": f"PERSON:laserai_{author_slug}",
            "agent_type": "Person",
            "family_name": str(first_author),
        }
    ]


def _core_schema_path() -> Path:
    """Locate the HEW core schema, which fully defines LiteratureResource."""
    try:
        from hew_model.jsonld import SCHEMA_PATH
    except ImportError as exc:
        raise ImportError(
            "The HEW model package is required for LaserAI JSON-LD output; "
            "install the accelerator_laserai requirements"
        ) from exc
    # hew_model defaults to hew-extended.yaml; the core hew.yaml sits beside it.
    return SCHEMA_PATH.with_name("hew.yaml")


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
        self.template_processor = AccelTemplateProcessor()

    @staticmethod
    def _load_jsonld_serializer() -> JsonLdSerializer:
        """Load the serializer from the reusable HEW model package."""
        schema_path = _core_schema_path()
        from hew_model.jsonld import to_jsonld

        return partial(to_jsonld, schema_path=schema_path)

    @staticmethod
    def _canonical_context() -> dict[str, Any]:
        """Load the JSON-LD context generated for the installed HEW schema."""
        schema_path = _core_schema_path()
        from hew_model.jsonld import generate_context

        context_document = generate_context(schema_path)
        context = context_document.get("@context")
        if not isinstance(context, dict):
            raise RuntimeError("The HEW model generated an invalid JSON-LD context")
        return context

    def transform(self, ingest_result: IngestPayload) -> IngestPayload:
        """Resolve and crosswalk every intermediate LaserAI record."""
        output_payload = IngestPayload(ingest_result.ingest_source_descriptor)
        payload_length = self.get_payload_length(ingest_result)

        for index in range(payload_length):
            input_record = self.payload_resolve(ingest_result, index)
            payload = input_record["data"]
            linkml_record = self.translate_to_linkml(payload)
            jsonld_record = self.jsonld_serializer(
                linkml_record,
                class_name="LiteratureResource",
            )
            if not jsonld_record.get("@context"):
                jsonld_record["@context"] = self._canonical_context()
            descriptor = ingest_result.ingest_source_descriptor
            source_metadata = input_record["technical_metadata"]
            source_submission = input_record["submission"]
            accelerator_record = self.template_processor.render_generic(
                jsonld_record,
                submission=source_submission,
                technical_metadata=source_metadata,
            )
            self.report_individual(
                output_payload, linkml_record["id"], accelerator_record
            )
            descriptor.ingest_item_id = source_metadata["original_source_identifier"]
            descriptor.ingest_link = source_metadata["original_source_link"]

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
            "identifiers": _unique_strings(
                [reference_number]
                + (bibliographic.get("study_identifiers") or [])
            ),
            "annotations": [
                self._annotation(payload, resource_id, reference_number, review)
            ],
        }

        subtitle = bibliographic.get("subtitle")
        if subtitle is not None:
            resource["subtitle"] = subtitle

        accession_number = bibliographic.get("accession_number")
        if accession_number is not None:
            accession = str(accession_number)
            if accession.isdigit():
                resource["pmid"] = accession
            else:
                resource["identifiers"].append(accession)

        publication_type = _enum_value(review.get("reference_type"), _REFERENCE_TYPES)
        if publication_type:
            resource["publication_type"] = publication_type

        year = bibliographic.get("year")
        if year is not None and re.fullmatch(r"\d{4}", str(year)):
            resource["publication_date"] = str(year)

        authors = _authors(bibliographic.get("first_author"))
        if authors:
            resource["authors"] = authors

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

        reference_type = _enum_value(review.get("reference_type"), _REFERENCE_TYPES)
        information_source = _enum_value(
            review.get("information_source"), _INFORMATION_SOURCES
        )
        if reference_type:
            annotation["reference_type"] = reference_type
        if information_source:
            annotation["information_source"] = information_source

        objectives = payload.get("study_objectives", [])
        if objectives:
            annotation["study_objective"] = objectives[0]
            if len(objectives) > 1:
                annotation["notes"] = "; ".join(str(value) for value in objectives[1:])

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
        geographic_locations, unmapped_locations = _closed_enum_values(
            locations,
            _GEOGRAPHIC_LOCATIONS,
        )
        geographic_features, unmapped_features = _closed_enum_values(
            features,
            _GEOGRAPHIC_FEATURES,
            aliases={"ocean_coastal": "ocean_coastal"},
        )
        if geographic_locations:
            geography_annotation["geographic_locations"] = geographic_locations
        if geographic_features:
            geography_annotation["geographic_features"] = geographic_features
        source_geography_text = _unique_strings(unmapped_locations + unmapped_features)
        if source_geography_text:
            geography_annotation["spatial_text"] = "; ".join(source_geography_text)
        annotation["geography_annotations"] = (
            [geography_annotation] if geography_annotation else []
        )

        data_and_models = payload.get("data_and_models", {})
        data_resource_types = data_and_models.get("data_resource_types", {})
        if not data_resource_types:
            data_resource_types = {
                "level_1": data_and_models.get("data_resource_types_level_1", []),
                "level_2": data_and_models.get("data_resource_types_level_2", []),
            }
        resource_types, _ = _closed_enum_values(
            _flatten_levels(data_resource_types, "level_1", "level_2"),
            _DATA_RESOURCE_TYPES,
        )
        model_types, _ = _closed_enum_values(
            data_and_models.get("model_types", []),
            _MODEL_TYPES,
        )
        data_tool_method_annotation = {}
        if resource_types:
            data_tool_method_annotation["data_resource_types"] = resource_types
        if model_types:
            data_tool_method_annotation["model_types"] = model_types
        annotation["data_tool_method_annotations"] = (
            [data_tool_method_annotation] if data_tool_method_annotation else []
        )

        special_topics = payload.get("special_topics", {})
        annotation["special_topic_annotations"] = _level_annotations(
            "special_topic", special_topics, self.term_mapper
        )

        return annotation
