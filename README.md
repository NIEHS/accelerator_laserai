# accelerator_laserai
LaserAI input connector for Accelerator

## HEW output mapping

The source component preserves each LaserAI spreadsheet record in the
Accelerator intermediate document shape. The crosswalk then emits the current
HEW `LiteratureResource` JSON-LD document inside the standard Mongo-compatible
Accelerator envelope:

```json
{
  "submission": {},
  "data": {
    "@type": "LiteratureResource",
    "id": "HEWRES:laserai_<reference_number>"
  },
  "technical_metadata": {}
}
```

Bibliographic identifiers map to HEW `doi`, `pmid`, and `identifiers`;
systematic-review coding remains under `annotations`. The extracted reference
type also populates `publication_type`, and the year populates
`publication_date` (the shared HEW resource publication date). An input
`subtitle`, when present, is preserved as the shared HEW `subtitle` field.
LaserAI exports only the first author's surname, which maps
to an inlined HEW 2.0 `Person` in `authors`
(`{"id": "PERSON:laserai_<surname>", "agent_type": "Person", "family_name": ...}`).
Output is validated and serialized against the canonical modular HEW schema
(`hew.yaml`) from the installed `hew-data-commons-model` package. The dependency
is pinned to commit `56c45b00f30d045361409b4314c1cc1868a499fa`, which includes the
Amadeus alignment and enum-only temporal resolution. Closed HEW enum values are
read from that schema rather than maintained separately in the crosswalk.
Review geography is retained as broad
annotation coding; labels that cannot be mapped safely are preserved in
`spatial_text` and are not promoted to exact structured locations.

Explicit `spatial_coverage`, `temporal_coverage`, `spatial_extent`, and
`temporal_extent` fields on enriched intermediate records are copied to the
HEW resource and validated before serialization. `temporal_resolution` in a
temporal extent accepts only Amadeus enum values such as `daily`, `hourly`, or
`timeless`; duration strings such as `P1D` and the removed
`temporal_resolution_category` slot are rejected. Invalid bounding boxes and
datetimes also fail validation. Publication year does not imply study coverage,
and the spreadsheet reader does not infer coordinates or time intervals from
broad review labels. Supplied datetime intervals follow HEW's inclusive-start,
exclusive-end convention.

LaserAI exposure, health-impact, and special-topic labels are matched against
a bundled HEW_Measures vocabulary snapshot using case- and punctuation-insensitive
exact matches of term titles and aliases. Unique matches use the canonical
`HEWM:<identifier>` term CURIE (for example, `HEWM:0000181` for Drought) and
include the vocabulary schema URI
(`https://w3id.org/hew/measures/schema`) and any available exact mappings.
The HEW model's JSON-LD context expands these CURIEs using
`https://w3id.org/hew/measures/term/`. Exposure and health-impact matches are
restricted to their corresponding vocabulary domains. Ambiguous and unmatched
labels are left as source text rather than guessed. The snapshot is packaged
with the connector so crosswalking does not require runtime network access.
