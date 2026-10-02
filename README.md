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
`publication_date`. LaserAI exports only the first author's surname, which maps
to an inlined HEW 2.0 `Person` in `authors`
(`{"id": "PERSON:laserai_<surname>", "agent_type": "Person", "family_name": ...}`).
Output is serialized against the HEW 2.0 core schema (`hew.yaml`). Closed HEW enum fields
are normalized to schema values. Review geography is retained as broad
annotation coding; labels that cannot be mapped safely are preserved in
`spatial_text` and are not promoted to exact structured locations.
