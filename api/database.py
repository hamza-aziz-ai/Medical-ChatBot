import os

from neo4j import GraphDatabase


def database_name():
    return os.environ.get("NEO4J_DATABASE", "neo4j")


def create_driver():
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise RuntimeError("NEO4J_PASSWORD must be set")

    return GraphDatabase.driver(
        os.environ.get("NEO4J_URI", "neo4j://localhost:7687"),
        auth=(os.environ.get("NEO4J_USER", "neo4j"), password),
        connection_timeout=10,
        max_transaction_retry_time=15,
    )
