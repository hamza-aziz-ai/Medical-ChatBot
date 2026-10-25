import math
import os

from neo4j import GraphDatabase

DEFAULT_QUERY_TIMEOUT = 5.0
BOLT_SCHEMES = frozenset({"bolt", "bolt+s", "bolt+ssc", "neo4j", "neo4j+s", "neo4j+ssc"})


def database_name():
    return os.environ.get("NEO4J_DATABASE", "neo4j")


def query_timeout():
    """Seconds a single API graph query may run before Neo4j aborts it."""
    raw = os.environ.get("NEO4J_QUERY_TIMEOUT")
    if raw is None:
        return DEFAULT_QUERY_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError("NEO4J_QUERY_TIMEOUT must be a positive number of seconds")
    return value


def database_uri():
    uri = os.environ.get("NEO4J_URI", "neo4j://localhost:7687")
    # Query timeouts only take effect over Bolt; the driver ignores them over HTTP.
    if uri.split("://", 1)[0] not in BOLT_SCHEMES:
        raise RuntimeError("NEO4J_URI must use a Bolt scheme: " + ", ".join(sorted(BOLT_SCHEMES)))
    return uri


def create_driver():
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise RuntimeError("NEO4J_PASSWORD must be set")

    return GraphDatabase.driver(
        database_uri(),
        auth=(os.environ.get("NEO4J_USER", "neo4j"), password),
        connection_timeout=10,
        max_transaction_retry_time=15,
    )
