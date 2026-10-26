# Dataset pilot: name overlap

Measured 2026-10-25 20:06 UTC at commit `1a8a2112bc3a` by `scripts/dataset_pilot.py` (D-011, measurement only).

**What this shows.** How many of our 658 disease names (`api/dictionary/entities.json`, SHA-256 `4ff981e4751d0c82…`, CSV source `031fda2f93925f67…`) appear, after NFKC, casefolding and collapsing whitespace, as a MedlinePlus English health-topic title or "also called" name, or as a Disease Ontology term name or EXACT synonym. Punctuation and plurals are kept and nothing fuzzy is counted.

**What it does not show.** A matched name is lexical overlap, not proof of the same condition. Neither source is shown to answer our seven question types, and MedlinePlus summaries are not established as clinically reviewed (A-08). "Unmatched" means this method found no match. The CSV's own rights (A-01) are unaffected.

| Source                                  | Diseases matched |
|-----------------------------------------|------------------|
| MedlinePlus                             | 83 (12.6%)       |
| Disease Ontology                        | 188 (28.6%)      |
| Either                                  | 207 (31.5%)      |
| Both                                    | 64 (9.7%)        |
| Neither                                 | 451 (68.5%)      |
| Matched more than one MedlinePlus topic | 0                |
| Matched more than one DOID term         | 1                |

**Sources.**

- MedlinePlus: `https://medlineplus.gov/xml/mplus_topics_2026-10-24.xml`, SHA-256 `be4c72d83bd9bda0144319b52e7c9410cc275df2d692b3e7812d5e3b46801577`, 1017 English of 2033 health topics. Topic data from MedlinePlus.gov; MedlinePlus invites reuse of its XML with attribution and states that health-topic summaries are public domain, while other material it links may be copyrighted.
- Disease Ontology: `https://raw.githubusercontent.com/DiseaseOntology/HumanDiseaseOntology/main/src/ontology/releases/doid.obo` (releases/2026-09-30/doid.obo), SHA-256 `51e717b6b9f5d391f2793f9e16faf9c8629a661ab8f21c3a024458129f182ad2`, 12335 usable of 14854 terms; licensed CC0 1.0.

The per-disease mappings are in `pilot-data/mappings.json`, which is not committed.

## Candidates (unreviewed)

Retrieved 2026-10-25 21:37 UTC at commit `dc13ebe909c1` by `scripts/dataset_pilot.py --candidates` in 28.2 s, from the cached files only: MedlinePlus SHA-256 `be4c72d83bd9bda0…`, Disease Ontology releases/2026-09-30/doid.obo SHA-256 `51e717b6b9f5d391…`, dictionary SHA-256 `ff3a1ac45f0e00be…` (CSV source `031fda2f93925f67…`).

**What this is.** Leads for the 451 names with no exact match, for the owner to review. Every candidate is unreviewed lexical retrieval: it may name a different condition, and a mistranslated name may get none. Nothing here is added to the matches above or counted as coverage. The methods' order only sorts each list; it is not clinical confidence. The per-name candidates are in `pilot-data/candidates.json`, which is not committed.

| Names                                     | Count |
|-------------------------------------------|-------|
| Searched (no exact match above)           | 451   |
| With at least one candidate               | 62    |
| With none                                 | 389   |
| With candidates for more than one concept | 17    |

| Method                | What it relaxes                                                                                                                                  | Names with a candidate from it (a name can count more than once) | Names whose first-listed candidate comes from it |
|-----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------|--------------------------------------------------|
| `punctuation_relaxed` | punctuation and hyphens read as spaces                                                                                                           | 1                                                                | 1                                                |
| `token_order_ignored` | also ignores word order, which can change the condition                                                                                          | 0                                                                | 0                                                |
| `doid_scoped`         | DOID RELATED, BROAD or NARROW synonyms; the scope is DOID's annotation, not a relation to our name                                               | 0                                                                | 0                                                |
| `qualifier_removed`   | one leading qualifier (acute, chronic, idiopathic, infantile, neonatal, pediatric, primary, secondary, simple) removed; no relationship asserted | 27                                                               | 27                                               |
| `similar`             | difflib ratio of at least 0.88, at most 3 concepts, only when nothing else matched                                                               | 34                                                               | 34                                               |

At a ratio of at least 0.93, 16 names have a `similar` candidate; 4 names had more than 3 similar concepts, and the rest are not listed. These thresholds are uncalibrated, so the counts are candidate volumes, not precision.
