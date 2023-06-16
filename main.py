import logging
from json_logger_stdout import json_std_logger
from collections import namedtuple
from functools import partial

from utils import (N_CHUNKS_TO_CONCAT_BEFORE_UPDATING, OPENAI_API_KEY,
                   num_tokens_from_messages, process_conversation_history,
                   update_chat)


from slack_bolt import App
import openai

logging.basicConfig(level=logging.DEBUG)
app = App()
openai.api_key = OPENAI_API_KEY

################################################

OPENAI_MODEL_DEFAULT = "gpt-3.5-turbo"
OPENAI_MODEL_MAX_TOKENS = 4096

OPENAI_MODEL_CROSSOVER_POINT = OPENAI_MODEL_MAX_TOKENS * 0.75

OPENAI_MODEL_EXTENDED = "gpt-3.5-turbo-16k"
OPENAI_MODEL_EXTENDED_MAX_TOKENS = 16384

################################################
def get_conversation_history(channel_id, thread_ts):
    return app.client.conversations_replies(
        channel=channel_id,
        ts=thread_ts,
        inclusive=True
    )

User = namedtuple('User', ('username', 'display_name', 'first_name', 'last_name', 'email'))
'''
This uses https://api.slack.com/methods/users.profile.get
'''
def get_user_information(user_id):
        result = app.client.users_info(
            user=user_id
        )

        return User(result['user']['name'], 
                result['user']['profile']['display_name'],
                result['user']['profile']['first_name'],
                result['user']['profile']['last_name'],
                result['user']['profile']['email'])

def build_personalized_wait_message(first_name):
    return "Hi " + first_name +"! " + "I got your request, please wait while I ask the wizard..."

def logging_wrapper(message, severity=logging.INFO, **kwargs):
    json_std_logger._setParams(**kwargs)

    log = {
        logging.DEBUG: json_std_logger.debug,
        logging.ERROR: json_std_logger.error,
        logging.CRITICAL: json_std_logger.critical,
        logging.WARNING: json_std_logger.warning
    }
    func = log.get(severity, json_std_logger.info)
    func(message)

'''
gpt-3.5-turbo-16k offers 4 times the context length of gpt-3.5-turbo at twice the price: 
$0.003 per 1K input tokens and $0.004 per 1K output tokens. 

So if the conversation exceeds the cutoff, then switch to using the extended model. Otherwise, use 
the standard model, as that seems fine for most conversations at this point.
'''
def determine_openai_model_to_use(input_token_count):
    if input_token_count > OPENAI_MODEL_CROSSOVER_POINT:
        return (OPENAI_MODEL_EXTENDED, OPENAI_MODEL_EXTENDED_MAX_TOKENS)
    else:
        return (OPENAI_MODEL_DEFAULT, OPENAI_MODEL_MAX_TOKENS)

def stream_openai_response_to_slack(openai_response, slack_update_func):
    response_text = ""
    ii = 0
    for chunk in openai_response:
        if chunk.choices[0].delta.get('content'):
            ii = ii + 1
            response_text += chunk.choices[0].delta.content
            if ii > N_CHUNKS_TO_CONCAT_BEFORE_UPDATING:
                slack_update_func(response_text)
                ii = 0
        elif chunk.choices[0].finish_reason == 'stop':
           slack_update_func(response_text)
    
    return response_text

################################################
@app.event("app_mention")
def handle_app_mentions(body, context):
    try:
        logging_wrapper("Arguments", logging.DEBUG, body=body, context=context)

        channel_id = body['event']['channel']
        thread_ts = body['event'].get('thread_ts', body['event']['ts'])
        print(f'thread_ts: {thread_ts}')
        bot_user_id = context['bot_user_id']
        user_id = context['user_id']

        user = get_user_information(user_id)

        '''
        How to lock the bot to a particular channel
        -------------------------------------------
        In this case, for the beta testing we created the channel,
        beta-slack-chatgpt-bot (channel_id: C057NBLL2G4). If the message
        didn't originate from this channel, you got a polite message and 
        were denied access.
        
        if channel_id != 'C057NBLL2G4': #lock to test channel for beta
            slack_resp = app.client.chat_postMessage( 
                channel=channel_id,
                thread_ts=thread_ts,
                text="Our apologies, however the Beta ChatGPT bot is not allowed outside of the beta-slack-chatgpt-bot channel"
            )
            return
        '''

        slack_resp = app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=build_personalized_wait_message(user.first_name)
        )

        reply_message_ts = slack_resp['message']['ts']
        conversation_history = get_conversation_history(channel_id, thread_ts)
        messages = process_conversation_history(conversation_history, bot_user_id)
        num_conversation_tokens = num_tokens_from_messages(messages, OPENAI_MODEL_DEFAULT)
        
        '''
        print(openai.Model.list())
        This API does not tell you anything about the number of tokens supported by the model, yet
        ...
        {
            "created": 1683758102,
            "id": "gpt-3.5-turbo-16k",
            "object": "model",
            "owned_by": "openai-internal",
            "parent": null,
            "permission": [
                {
                "allow_create_engine": false,
                "allow_fine_tuning": false,
                "allow_logprobs": true,
                "allow_sampling": true,
                "allow_search_indices": false,
                "allow_view": true,
                "created": 1686799823,
                "group": null,
                "id": "modelperm-LMK1z45vFJF9tVUvKb3pZfMG",
                "is_blocking": false,
                "object": "model_permission",
                "organization": "*"
                }
            ],
            "root": "gpt-3.5-turbo-16k"
        },
        '''

        #Pick the model to use based on the number of tokens used thus far
        #picking the extended model, means spending more, so only select that when 
        #necessary
        model, token_count = determine_openai_model_to_use(num_conversation_tokens)

        max_response_tokens = token_count-num_conversation_tokens
        openai_response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_response_tokens #if this drops below 0, openai should throw an exception
        )
        
        slack_update_func = partial(update_chat, app, channel_id, reply_message_ts)
        response_text = stream_openai_response_to_slack(openai_response, slack_update_func)

        logging_wrapper("RequestResponse", logging.INFO,
            model_used=model,
            token_used_count=num_conversation_tokens,
            max_response_tokens=max_response_tokens,
            channel_id=channel_id,
            thread_ts=thread_ts,
            user=user.username, 
            email=user.email,
            request=messages[1:],   #field 0 is something that gets added as part of process_conversation_history that we don't need
            response=response_text
        )
    
    except Exception as e:
        logging_wrapper("Exception", logging.ERROR, 
            token_used_count=num_conversation_tokens,
            max_response_tokens=max_response_tokens,
            channel_id=channel_id, 
            thread_ts=thread_ts,
            user=user.username, 
            email=user.email,
            request=messages[1:],
            exception=e
        )
        app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"Sorry, I can't provide a response. Encountered an error:\n`\n{e}\n`")

# @app.command("/hello-bolt-python")
# def hello(body, ack):
#     user_id = body["user_id"]
#     ack(f"Hi <@{user_id}>!")

################################################
from flask import Flask, request
from slack_bolt.adapter.flask import SlackRequestHandler

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    print('slack event received')
    return handler.handle(request)
