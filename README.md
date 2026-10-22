# Medical-ChatBot

## Setup

The API and the graph builder read the Neo4j password from the environment:

```
export NEO4J_PASSWORD=<your neo4j password>
```

The training notebooks expect the Quora Question Pairs data at `notebooks/data/train.csv`. It is not committed; download it from Kaggle (requires a Kaggle API token and accepting the competition rules):

```
kaggle competitions download -c quora-question-pairs -p notebooks/data
```

Unzip the download so that `notebooks/data/train.csv` exists.
