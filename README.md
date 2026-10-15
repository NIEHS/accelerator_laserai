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
Output is serialized against the HEW 2.0 core schema (`hew.yaml`). Closed HEW enum fields
are normalized to schema values. Review geography is retained as broad
annotation coding; labels that cannot be mapped safely are preserved in
`spatial_text` and are not promoted to exact structured locations.

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
