# DEFENSE: Medical-ChatBot (Mr. Healthcare)

**What it does.** It answers basic questions about diseases and symptoms (symptoms, causes, prevention, treatments, complications, descriptions) from a knowledge graph of 658 diseases. When the graph has no answer, it says so instead of guessing.

**How it works.** The page sends the question to a Flask API. The API finds known disease and symptom names in the question with an Aho-Corasick automaton, works out the intent from whole-word keywords, runs a fixed parameterized Cypher query against Neo4j, and turns the rows into a sentence. The graph is rebuilt from a CSV by an importer that validates the data and replaces only its own snapshot. See FLOW.md.

**Key decisions and why X over Y.**
- Graph and templates over a generative model: every answer is an inspectable query result, at the cost of understanding fewer phrasings.
- Abstaining over the old similarity fallback: the fallback returned other patients' answers to unrelated questions.
- Quarantining bad data over repairing it: no invented medical terms.
- No authentication over a shared token or accounts: the API is read-only over public data and only listens on this machine, so a token protected nothing and added friction; nginx rate-limits floods instead.
- Native path filters over a CI orchestrator: nothing runs for docs-only changes.

**Data structures and why.** A Neo4j graph with unique-name constraints, because every lookup is "facts about this named disease or symptom". An in-memory Aho-Corasick automaton, because it finds every known name in one pass over the question. See DATA.md.

**How a malicious actor could abuse it.** Anyone who can reach it can only send rate-limited, 500-character GET questions, which become query parameters, never query text. Answers render as plain text, and questions and tokens never reach a log. The real gaps are no authentication if it were ever exposed beyond this machine, auto-merging without human review, and a dataset whose facts are not clinically reviewed. See THREAT.md.

**Where it fails and how we notice.** If Neo4j is down or slow, users get a 503 message and the error is logged. A stale or empty graph makes every answer an abstention, which the CI evaluation catches but the Docker healthcheck does not. The first limit under load is the single gunicorn worker. There is no alerting. See FAILURE.md.

**What I would change with more time.** Replace the unverified CSV with sourced data (MedlinePlus + Disease Ontology, behind rights and evaluation gates). Move the question out of the URL into a POST body so proxies could keep logs. Add rate limiting and a graph-readiness health check. Publish the graph and dictionary as one unit (D35).
