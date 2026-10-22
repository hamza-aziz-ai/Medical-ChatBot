import json

from flask import Flask, request
from flask_cors import CORS

from chatbot_graph_logic import ChatBotGraph

application = Flask(__name__)
CORS(application)

handler = ChatBotGraph()


@application.route("/", methods=["GET", "POST"])
def home():
    search_term = request.args.get("search", '')

    data = {
        "search": search_term,
        "message": handler.chat_main(search_term)
    }
    # print(data)

    return json.dumps(data)
