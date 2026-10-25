# DATA

Key structures, how they are accessed, how big they get, and who writes them.

| Structure | Shape | Access pattern | Size today | Written by | Trade-off |
|---|---|---|---|---|---|
| Neo4j knowledge graph | Nodes `Disease` (name, description, prevention, causes, cure_department, cure_way, lineage), `Symptom`, `Department`; edges `has_symptom`, `accompany_with`, `disease_belongs_to`, `belongs_to`; every node and edge has `owner` | Read-only parameterized lookups by unique `name`, max 20 rows | 2,473 nodes, 5,301 relationships | Importer only (owned snapshot) | Unique-name index gives fast lookups; one transaction rebuild is simple but rewrites everything |
| `api/dictionary/entities.json` | Three sorted name lists plus the CSV hash | Loaded once at API start into an Aho-Corasick automaton | 658 diseases, 1,772 symptoms, 43 departments | Importer (atomic `os.replace`) | Linear-time multi-name matching; needs an API restart after an import |
| Aho-Corasick automaton (in memory) | Trie of all names with their types | Scans the question once; whole-word, longest-span filtering | ~2,470 patterns | Built at start from `entities.json` | Fast and explainable; only exact (case-insensitive) names match |
| `api/data/medical.csv` | 672 rows, 9 columns; list cells are Python literals | Read once per import | 3.4 MB | Nobody at runtime; source unknown (D30) | Simple file; unverified content |
| `eval/cases.jsonl`, `eval/baseline.json` | Reviewed questions with expected intents, entities, facts or abstention; expected import counts | Read by `scripts/evaluate_kg.py` | 14 cases; 12 counts | Humans, in reviewed commits only | Small set catches regressions, not clinical quality |
| `api/data/questions.json` | Question–answer records from questiondoctors.com | Not used at runtime | 5,679 records, 4 MB | Historical | Kept as a record; rights unknown (A-02) |
| Logs | `logs/<year>/<Month>/<module>.log`, rotated at midnight | Append only | Bounded by `LOG_BACKUP_COUNT` (30) | Each backend module | Easy to find per module; no questions or secrets |
