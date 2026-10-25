import atexit
import ipaddress
import logging
import os
import re

from flask import Flask, json, jsonify, request
from flask_cors import CORS
from neo4j.exceptions import ClientError, ServiceUnavailable, SessionExpired
from werkzeug.exceptions import HTTPException

MAX_QUESTION_LENGTH = 500
MAX_NAME_LENGTH = 200
MAX_SELECTIONS = 10
DEFAULT_ORIGINS = "http://localhost:8080,http://127.0.0.1:8080"
ORIGIN_PATTERN = re.compile(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?")
GRAPH_UNAVAILABLE = "The knowledge graph is unavailable. Please try again later."

logger = logging.getLogger(__name__)

# The dev server's access log prints the full URL, which contains the question.
logging.getLogger("werkzeug").setLevel(logging.WARNING)


def allowed_origins():
    origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]
    for origin in origins:
        if not ORIGIN_PATTERN.fullmatch(origin):
            raise RuntimeError(f"CORS_ORIGINS must list exact http(s) origins such as http://localhost:8080, not {origin!r}")
    # Flask-Cors treats strings as patterns, so pass anchored literal patterns.
    return [re.compile("^" + re.escape(origin) + "$") for origin in origins]


def topic_from(args):
    name, entity_type = args.get("topic", ""), args.get("topic_type", "")
    if not name or len(name) > MAX_NAME_LENGTH:
        return None
    return {"name": name, "type": entity_type}


def selections_from(args):
    """selection=<name>:<type>, repeatable; malformed or excess values are ignored."""
    selections = []
    for value in args.getlist("selection")[:MAX_SELECTIONS]:
        name, _, entity_type = value.rpartition(":")
        if name and len(name) <= MAX_NAME_LENGTH:
            selections.append({"name": name, "type": entity_type})
    return selections


def client_address(request):
    """The client's address for the suggestion budget (D-025), never logged.

    X-Real-IP is trusted only where TRUST_PROXY_HEADER=1, which the API image sets because only nginx can reach it
    there and nginx overwrites the header. Direct development uses the socket address, so a sent header is ignored.
    """
    candidates = [request.headers.get("X-Real-IP", "")] if os.environ.get("TRUST_PROXY_HEADER") == "1" else []
    for value in candidates + [request.remote_addr or ""]:
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:
            continue
    return "unknown"


def create_app(chatbot=None):
    if chatbot is None:
        import app_logging
        import database
        loaded = database.load_env_file()
        app_logging.setup_logging()
        database.log_env_loaded(loaded)

    origins = allowed_origins()

    if chatbot is None:
        from chatbot_graph_logic import ChatBotGraph
        chatbot = ChatBotGraph()
        atexit.register(chatbot.searcher.close)

    app = Flask(__name__)
    CORS(app, origins=origins, allow_headers=["Content-Type"])
    logger.info("API started; %d allowed CORS origin(s)", len(origins))

    @app.route("/", methods=["GET"])
    def home():
        # No authentication: the API is read-only over public data and listens on loopback only
        # (D-013); flood protection is nginx rate limiting. Never log the question itself.
        search_term = request.args.get("search", "").strip()
        if not search_term:
            logger.info("Rejected request: empty question")
            return jsonify(error="Ask a question using the 'search' parameter."), 400
        if len(search_term) > MAX_QUESTION_LENGTH:
            logger.info("Rejected request: question of %d characters is too long", len(search_term))
            return jsonify(error=f"Questions are limited to {MAX_QUESTION_LENGTH} characters."), 400

        # D-023: never answer from a graph that is not the one this API's dictionary was published with. The check
        # and the answer queries are separate, so imports still run with serving stopped (see docs/ROLLBACK.md).
        ready, reason = chatbot.ready()
        if not ready:
            logger.warning("Refused a question: %s", reason)
            return jsonify(error=GRAPH_UNAVAILABLE), 503

        logger.debug("Answering a question of %d characters", len(search_term))
        # The page sends back the confirmed topic and any clarification choices; the chatbot checks both
        # against the dictionary and this question. Like the question, they are never logged.
        reply = chatbot.respond(search_term, topic=topic_from(request.args), selections=selections_from(request.args),
                                client=client_address(request))
        logger.info("Replied (%s) to a question of %d characters", reply["status"], len(search_term))
        return jsonify(search=search_term, **reply)

    @app.route("/health", methods=["GET"])
    def health():
        # D-022: ok only while the graph holds the dictionary's diseases from the same CSV. Docker's healthcheck
        # calls this every 30 s, so success is not logged; the body never says more than ok or unavailable.
        ready, reason = chatbot.ready()
        if ready:
            return jsonify(status="ok")
        logger.warning("Not ready: %s", reason)
        return jsonify(status="unavailable"), 503

    @app.errorhandler(HTTPException)
    def http_error(error):
        # Keep the exception's headers (for example Allow on 405); replace only the body.
        response = error.get_response()
        response.data = json.dumps({"error": error.description})
        response.content_type = "application/json"
        return response

    @app.errorhandler(ServiceUnavailable)
    @app.errorhandler(SessionExpired)
    def graph_unavailable(error):
        app.logger.error("Knowledge graph unavailable (%s)", type(error).__name__)
        return jsonify(error=GRAPH_UNAVAILABLE), 503

    @app.errorhandler(ClientError)
    def graph_client_error(error):
        if "TransactionTimedOut" in (error.code or ""):
            app.logger.error("Knowledge graph query timed out")
            return jsonify(error=GRAPH_UNAVAILABLE), 503
        app.logger.error("Knowledge graph client error (%s)", type(error).__name__)
        return jsonify(error="Something went wrong. Please try again."), 500

    @app.errorhandler(Exception)
    def unexpected_error(error):
        # Log the type only: exception messages can echo the question.
        app.logger.error("Unhandled %s", type(error).__name__)
        return jsonify(error="Something went wrong. Please try again."), 500

    return app
