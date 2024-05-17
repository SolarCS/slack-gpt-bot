import logging
from json_logger_stdout import json_std_logger
from collections import namedtuple
from functools import partial

from utils import (N_CHUNKS_TO_CONCAT_BEFORE_UPDATING, OPENAI_API_KEY,
                   num_tokens_from_messages, process_conversation_history,
                   update_chat)

from openai import OpenAI

#Logging Configuration
DEBUG = False
if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
    json_std_logger.setLevel (logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)
    json_std_logger.setLevel (logging.INFO)

################################################
#-----------------------------------------------
# GPT 4 Models
OPENAI_MODEL_4_OHHHH = "gpt-4o"
OPENAI_MODEL_4_OHHHH_TOKENS = 128000

#-----------------------------------------------
# Model to use
OPENAI_MODEL_IN_USE = OPENAI_MODEL_4_OHHHH
################################################

User = namedtuple('User', ('user_id','username','real_name','email'))
class SlackGPTBot:
    def __init__(self, app, model_to_use=OPENAI_MODEL_4_OHHHH, model_tokens=OPENAI_MODEL_4_OHHHH_TOKENS):
        self.app = app
        self.model_to_use = model_to_use
        self.model_tokens = model_tokens
        self.openai_client = OpenAI(
            api_key=OPENAI_API_KEY
        )

    def get_conversation_history(self, channel_id, thread_ts):
        return self.app.client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            inclusive=True
        )

    '''
    This uses https://api.slack.com/methods/users.profile.get
    '''
    def get_user_information(self, user_id):
            user_info = self.app.client.users_info(
                user=user_id
            )

            user = None
            try:
                # user_info['user]['profile']['first_name'] - not guaranteed
                # user_info['user]['profile']['last_name'] - not guaranteed

                user = User(user_id, user_info['user']['name'], 
                            user_info['user']['profile']['first_name'],
                            user_info['user']['profile']['email'])
            except KeyError as e:
                #-In the event that Slack deprecates a field
                self.logging_wrapper("Slack_Warning",logging.WARNING, 
                                     user_id=user_id,
                                     exception="KeyError: " + str(e),
                                     profile=user_info)
                user = User(user_id, "", "", "")
            finally:
                return user

    def build_personalized_wait_message(self, real_name):
        first_name = self.extract_first_name(real_name)
        return "Hi " + first_name +"! " + "I got your request, please wait while I ask the wizard..."

    # Write a method that takes a user's real name, a string in the format of "first last", and extract the first part 
    # of the string. Be sure to handle the case where the real name is just "first" and the case where real name is "".
    def extract_first_name(self, real_name):
        if real_name == "":
            return ""
        else:
            return real_name.split()[0]

    '''
    This method is used to log messages to the console and to the json_logger_stdout
    '''
    def logging_wrapper(self, message, severity=logging.INFO, **kwargs):
        json_std_logger._setParams(**kwargs)

        log = {
            logging.DEBUG: json_std_logger.debug,
            logging.ERROR: json_std_logger.error,
            logging.CRITICAL: json_std_logger.critical,
            logging.WARNING: json_std_logger.warning
        }
        func = log.get(severity, json_std_logger.info)
        func(message)

    def stream_openai_response_to_slack(self, openai_response, slack_update_func):
        response_text = ""
        ii = 0
        for chunk in openai_response:
            if chunk.choices[0].delta.content is not None:
                ii = ii + 1
                response_text += chunk.choices[0].delta.content
                if ii > N_CHUNKS_TO_CONCAT_BEFORE_UPDATING:
                    slack_update_func(response_text)
                    ii = 0
            elif chunk.choices[0].finish_reason == 'stop':
                slack_update_func(response_text)
        
        return response_text

    ################################################
    # @app.event("app_mention")
    def handle_app_mentions(self, body, context):
        num_conversation_tokens = None
        max_response_tokens = None
        channel_id = None
        thread_ts = None
        token_count = None

        try:
            self.logging_wrapper("Arguments", logging.DEBUG, body=body, context=context)

            channel_id = body['event']['channel']
            thread_ts = body['event'].get('thread_ts', body['event']['ts'])
            bot_user_id = context['bot_user_id']
            user_id = context['user_id']

            #Impersonate A User Here

            self.logging_wrapper("Milestone", logging.DEBUG, 
                    milestone="Fetching user information from slack",
                    user_id=user_id)
            user = self.get_user_information(user_id)

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
            slack_resp = self.app.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=self.build_personalized_wait_message(user.real_name)
            )

            self.logging_wrapper("Milestone", logging.DEBUG, 
                    milestone="Fetching conversation history from slack",
                    user_id=user_id,
                    email=user.email,
                    channel=channel_id,
                    thread_ts=thread_ts)

            reply_message_ts = slack_resp['message']['ts']
            conversation_history = self.get_conversation_history(channel_id, thread_ts)

            self.logging_wrapper("Milestone", logging.DEBUG, 
                    milestone="Processing conversation history from slack",
                    user_id=user_id,
                    email=user.email,
                    channel=channel_id,
                    thread_ts=thread_ts)
            messages = process_conversation_history(conversation_history, bot_user_id)

            self.logging_wrapper("Milestone", logging.DEBUG, 
                    milestone="Counting tokens",
                    messages=messages)
            num_conversation_tokens = num_tokens_from_messages(messages, self.model_to_use)
            
            '''
            print(openai.Model.list())
            This API does not tell you anything about the number of tokens supported by the model
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

            self.logging_wrapper("Milestone", logging.DEBUG, 
                    milestone="Determining OpenAI Model to use",
                    num_conversation_tokens=num_conversation_tokens)

            #Pick the model to use based on the number of tokens used thus far
            #picking the extended model, means spending more, so only select that when 
            #necessary
            # model, token_count = OPENAI_MODEL_4_OHHHH, OPENAI_MODEL_4_OHHHH_TOKENS)

            max_response_tokens = self.model_tokens-num_conversation_tokens
            self.logging_wrapper("Milestone", logging.DEBUG, 
                            milestone="Forwarding request to OpenAI",
                            model_used=self.model_to_use,
                            token_count=self.model_tokens,
                            token_used_count=num_conversation_tokens,
                            user_id=user_id,
                            email=user.email,
                            request=messages[-1])
    
            openai_response = self.openai_client.chat.completions.create(
                model=self.model_to_use,
                messages=messages,
                stream=True
            )

            slack_update_func = partial(update_chat, self.app, channel_id, reply_message_ts)
            response_text = self.stream_openai_response_to_slack(openai_response, slack_update_func)

            self.logging_wrapper("RequestResponse", logging.INFO,
                model_used=self.model_to_use,
                token_used_count=num_conversation_tokens,
                max_response_tokens=max_response_tokens,
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user_id,
                user=user.username, 
                email=user.email,
                request=messages[-1],   #Get the last request from the messages array
                response=response_text
            )
        
        except Exception as e:
            self.logging_wrapper("Exception", logging.ERROR, 
                model_used=self.model_to_use,
                token_used_count=num_conversation_tokens,
                max_response_tokens=max_response_tokens,
                channel_id=channel_id, 
                thread_ts=thread_ts,
                user_id=user_id,
                user=user.username, 
                email=user.email,
                request=messages[-1],
                exception=e
            )
            self.app.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f"Sorry, I can't provide a response. Encountered an error:\n`\n{e}\n`")
