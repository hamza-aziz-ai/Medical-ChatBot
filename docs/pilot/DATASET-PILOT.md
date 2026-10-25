# Dataset pilot: name overlap

Measured 2026-10-25 20:06 UTC at commit `1a8a2112bc3a` by `scripts/dataset_pilot.py` (D-011, measurement only).

**What this shows.** How many of our 658 disease names (`api/dictionary/entities.json`, SHA-256 `4ff981e4751d0c82…`, CSV source `031fda2f93925f67…`) appear, after NFKC, casefolding and collapsing whitespace, as a MedlinePlus English health-topic title or "also called" name, or as a Disease Ontology term name or EXACT synonym. Punctuation and plurals are kept and nothing fuzzy is counted.

**What it does not show.** A matched name is lexical overlap, not proof of the same condition. Neither source is shown to answer our seven question types, and MedlinePlus summaries are not established as clinically reviewed (A-08). "Unmatched" means this method found no match. The CSV's own rights (A-01) are unaffected.

| Source | Diseases matched |
|---|---|
| MedlinePlus | 83 (12.6%) |
| Disease Ontology | 188 (28.6%) |
| Either | 207 (31.5%) |
| Both | 64 (9.7%) |
| Neither | 451 (68.5%) |
| Matched more than one MedlinePlus topic | 0 |
| Matched more than one DOID term | 1 |

**Sources.**

- MedlinePlus: `https://medlineplus.gov/xml/mplus_topics_2026-10-24.xml`, SHA-256 `be4c72d83bd9bda0144319b52e7c9410cc275df2d692b3e7812d5e3b46801577`, 1017 English of 2033 health topics. Topic data from MedlinePlus.gov; MedlinePlus invites reuse of its XML with attribution and states that health-topic summaries are public domain, while other material it links may be copyrighted.
- Disease Ontology: `https://raw.githubusercontent.com/DiseaseOntology/HumanDiseaseOntology/main/src/ontology/releases/doid.obo` (releases/2026-09-30/doid.obo), SHA-256 `51e717b6b9f5d391f2793f9e16faf9c8629a661ab8f21c3a024458129f182ad2`, 12335 usable of 14854 terms; licensed CC0 1.0.

The per-disease mappings are in `pilot-data/mappings.json`, which is not committed.
