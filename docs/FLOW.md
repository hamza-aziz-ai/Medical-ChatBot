# FLOW

How execution travels. Update this when a path changes, and mark the functions a change touches.

## A question (runtime)

```
frontend/src/components/ChatPanel.vue  submit()            Enter or Send; blocks empty, over-long and duplicate submits
  -> frontend/src/App.vue              messageSendHandler()
  -> frontend/src/chatApi.mjs          sendMessage() -> fetchHttp.get()   GET {base}/?search=..., Bearer token, 10 s timeout
  -> docker/nginx.conf                 location /api/  (Docker only; strips /api, logs nothing)
  -> api/main.py                       home()           token check (constant time), empty and 500-char checks
  -> api/chatbot_graph_logic.py        ChatBotGraph.chat_main()
       -> api/question_classifier.py   QuestionClassifier.classify()
            check_medical()            Aho-Corasick entity spans, whole words only
            check_words()              keyword intents, whole words only
          no entity, or an unsupported intent -> ABSTENTION
       -> api/question_parser.py       QuestionParser.parser_main() -> sql_transfer()   template + {name, limit: 20}
       -> api/answer_searcher.py       AnswerSearcher.search_main()   execute_query, READ routing, query timeout (5 s default)
            answer_prettify()          group by subject, drop artefact terms, cap 20 values
          no rows -> ABSTENTION
  <- api/main.py                       jsonify({search, message})
  <- frontend                          appends the reply as plain text; errors become fixed messages
```

Errors: Neo4j unavailable, session expired or transaction timeout give 503 with a fixed message; anything else gives a sanitized 500. Only the exception type is logged.

## A graph import

```
api/build_medicalgraph.py main()
  -> load_dataset()        required columns, no unnamed rows, field-level quarantine, conflicting names excluded, source hash
  -> graph_data()          nodes and edges; skips self-complications, collapses repeated departments, refuses department cycles
  -> print_report()
  -> stage_entities()      entities.json written to a temp file
  -> existing_conflicts()  refuses if unowned data collides with the snapshot
  -> create_constraints()
  -> write_graph()         one transaction (120 s): delete owned snapshot, recreate it
  -> publish_entities()    os.replace of entities.json
```

## The MLOps gate

```
.github/workflows/mlops.yml -> data gate tests -> live tests (Neo4j 5, 4.4) -> import (Neo4j 5)
  -> scripts/evaluate_kg.py: integrity_checks() + evaluate() -> eval-report.json (counts and IDs only)
```
