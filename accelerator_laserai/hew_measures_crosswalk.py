"""Exact-match lookup for the published HEW_Measures vocabulary."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_VOCABULARY_PATH = Path(__file__).parent / "resources" / "hew_measures_terms.json"
_CATEGORY_FILTERS = {
    "exposure": {"Environment", "Exposures"},
    "health_impact": {"Health"},
}
_IGNORED_LABELS = {"not found", "not in", "not reported"}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


@dataclass(frozen=True)
class HEWMeasuresTerm:
    """A HEW_Measures term and the metadata needed for HEW annotations."""

    identifier: str
    title: str
    aliases: tuple[str, ...]
    exact_mappings: tuple[str, ...]
    category: str


class HEWMeasuresTermMapper:
    """Map exact LaserAI labels and aliases to canonical HEW_Measures CURIEs."""

    def __init__(self, vocabulary_path: Path = _VOCABULARY_PATH):
        with vocabulary_path.open(encoding="utf-8") as vocabulary_file:
            vocabulary = json.load(vocabulary_file)

        self.vocabulary_uri = vocabulary["vocabulary_uri"]
        raw_terms = vocabulary["terms"]
        if not isinstance(raw_terms, list):
            raise ValueError("HEW_Measures vocabulary terms must be a list")

        self._terms: dict[str, HEWMeasuresTerm] = {}
        for raw_term in raw_terms:
            if not isinstance(raw_term, dict):
                raise ValueError("HEW_Measures vocabulary term must be an object")
            identifier = raw_term.get("id")
            title = raw_term.get("title")
            aliases = raw_term.get("aliases", [])
            exact_mappings = raw_term.get("exact_mappings", [])
            category = raw_term.get("category")
            if not isinstance(identifier, str) or not identifier.startswith("HEWM:"):
                raise ValueError("HEW_Measures vocabulary term must have a HEWM identifier")
            if not isinstance(title, str) or not title:
                raise ValueError("HEW_Measures vocabulary term must have a title")
            if not isinstance(aliases, list) or not all(
                isinstance(alias, str) for alias in aliases
            ):
                raise ValueError("HEW_Measures vocabulary term aliases must be strings")
            if not isinstance(exact_mappings, list) or not all(
                isinstance(mapping, str) for mapping in exact_mappings
            ):
                raise ValueError(
                    "HEW_Measures vocabulary term exact mappings must be strings"
                )
            if not isinstance(category, str) or not category:
                raise ValueError("HEW_Measures vocabulary term must have a category")
            if identifier in self._terms:
                raise ValueError(f"Duplicate HEW_Measures term identifier: {identifier}")
            self._terms[identifier] = HEWMeasuresTerm(
                identifier=identifier,
                title=title,
                aliases=tuple(aliases),
                exact_mappings=tuple(exact_mappings),
                category=category,
            )

        self._labels: dict[str, set[str]] = {}
        for term in self._terms.values():
            for label in (term.title, *term.aliases):
                normalized = _normalize(label)
                if normalized and normalized not in _IGNORED_LABELS:
                    self._labels.setdefault(normalized, set()).add(term.identifier)

    def match(self, category: str, value: str) -> HEWMeasuresTerm | None:
        """Return a unique category-compatible term, or None when uncertain."""
        candidates = self._labels.get(_normalize(value), set())
        permitted_categories = _CATEGORY_FILTERS.get(category)
        if permitted_categories:
            candidates = {
                identifier
                for identifier in candidates
                if self._terms[identifier].category in permitted_categories
            }
        if len(candidates) != 1:
            return None
        return self._terms[next(iter(candidates))]

    def __call__(self, category: str, value: str) -> str:
        term = self.match(category, value)
        return term.identifier if term else value

    def annotation_metadata(self, category: str, value: str) -> dict[str, Any]:
        """Return HEW model metadata for a matched vocabulary term."""
        term = self.match(category, value)
        if term is None:
            return {}

        metadata: dict[str, Any] = {
            "source_vocabularies": [self.vocabulary_uri],
            "aliases": list(dict.fromkeys((term.title, *term.aliases, value))),
        }
        if term.exact_mappings:
            metadata["exact_mappings"] = list(term.exact_mappings)
        return metadata
