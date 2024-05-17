'''
Slack GPT Chat Bot
Powered by a Slack Request URL, /slack/events, and the Python Flask framework
'''

from slack_gpt_bot import (SlackGPTBot)
from slack_bolt import App

app = App()
slack_gpt_bot = SlackGPTBot(app)

################################################

@app.event("app_mention")
def handle_app_mentions(body, context):
    slack_gpt_bot.handle_app_mentions(body, context)

from flask import Flask, request
from slack_bolt.adapter.flask import SlackRequestHandler

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)
