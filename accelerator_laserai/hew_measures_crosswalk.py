"""Exact-match lookup for the published HEW_Measures vocabulary."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_VOCABULARY_PATH = Path(__file__).parent / "resources" / "hew_measures_terms.json"
_CATEGORY_ROOTS = {
    "exposure": {"Environment", "Exposures"},
    "health_impact": {"Health"},
}
_IGNORED_LABELS = {"not found", "not in", "not reported"}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


@dataclass(frozen=True)
class HEWMeasuresTerm:
    """A HEW_Measures term and the metadata needed for HEW annotations."""

    name: str
    aliases: tuple[str, ...]
    exact_mappings: tuple[str, ...]
    parent: str | None

    def uri(self, vocabulary_prefix: str) -> str:
        return f"{vocabulary_prefix}{self.name}"


class HEWMeasuresTermMapper:
    """Map exact LaserAI labels and HEW_Measures aliases to canonical term URIs."""

    def __init__(self, vocabulary_path: Path = _VOCABULARY_PATH):
        with vocabulary_path.open(encoding="utf-8") as vocabulary_file:
            vocabulary = json.load(vocabulary_file)

        self.vocabulary_uri = vocabulary["vocabulary_uri"]
        self.vocabulary_prefix = vocabulary["vocabulary_prefix"]
        raw_terms = vocabulary["terms"]
        if not isinstance(raw_terms, list):
            raise ValueError("HEW_Measures vocabulary terms must be a list")

        self._terms: dict[str, HEWMeasuresTerm] = {}
        for raw_term in raw_terms:
            if not isinstance(raw_term, dict):
                raise ValueError("HEW_Measures vocabulary term must be an object")
            name = raw_term.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError("HEW_Measures vocabulary term must have a name")
            self._terms[name] = HEWMeasuresTerm(
                name=name,
                aliases=tuple(raw_term.get("aliases", [])),
                exact_mappings=tuple(raw_term.get("exact_mappings", [])),
                parent=raw_term.get("is_a"),
            )

        self._labels: dict[str, set[str]] = {}
        for term in self._terms.values():
            for label in (term.name, *term.aliases):
                normalized = _normalize(label)
                if normalized and normalized not in _IGNORED_LABELS:
                    self._labels.setdefault(normalized, set()).add(term.name)

    def _root_category(self, term: HEWMeasuresTerm) -> str | None:
        name = term.name
        visited = set()
        while name in self._terms and name not in visited:
            visited.add(name)
            parent = self._terms[name].parent
            if parent == "Category":
                return name
            if parent is None:
                return None
            name = parent
        return None

    def match(self, category: str, value: str) -> HEWMeasuresTerm | None:
        """Return a unique category-compatible term, or None when uncertain."""
        candidates = self._labels.get(_normalize(value), set())
        permitted_roots = _CATEGORY_ROOTS.get(category)
        if permitted_roots:
            candidates = {
                name
                for name in candidates
                if self._root_category(self._terms[name]) in permitted_roots
            }
        if len(candidates) != 1:
            return None
        return self._terms[next(iter(candidates))]

    def __call__(self, category: str, value: str) -> str:
        term = self.match(category, value)
        return term.uri(self.vocabulary_prefix) if term else value

    def annotation_metadata(self, category: str, value: str) -> dict[str, Any]:
        """Return HEW model metadata for a matched vocabulary term."""
        term = self.match(category, value)
        if term is None:
            return {}

        metadata: dict[str, Any] = {"source_vocabularies": [self.vocabulary_uri]}
        if _normalize(value) != _normalize(term.name):
            metadata["aliases"] = [value]
        if term.exact_mappings:
            metadata["exact_mappings"] = list(term.exact_mappings)
        return metadata
