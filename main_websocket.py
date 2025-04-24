'''
Slack GPT Chat Bot
Powered by a Slack Websockets
'''
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from slack_gpt_bot import (SlackGPTBot)
from utils import (SLACK_BOT_TOKEN, SLACK_APP_TOKEN)

app = App(token=SLACK_BOT_TOKEN)
slack_gpt_bot = SlackGPTBot(app)

################################################

@app.event("app_mention")
def handle_app_mentions(body, context):
    slack_gpt_bot.handle_app_mentions(body, context)

################################################
if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
