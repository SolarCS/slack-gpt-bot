import os
import re

import tiktoken
from trafilatura import extract, fetch_url
from trafilatura.settings import use_config

import logging
from json_logger_stdout import json_std_logger

logging.basicConfig(level=logging.DEBUG)
json_std_logger.setLevel (logging.DEBUG)

newconfig = use_config()
newconfig.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SYSTEM_PROMPT = '''
You are an AI assistant. 
You will answer the question as truthfully as possible.
If you're unsure of the answer, say Sorry, I don't know.
'''
WAIT_MESSAGE = "Got your request. Please wait."
N_CHUNKS_TO_CONCAT_BEFORE_UPDATING = 20
MAX_TOKENS = 8192

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

def extract_url_list(text):
    logging_wrapper("Milestone", logging.DEBUG, function="extract_url_list", text=text)
    
    #prone to catastrophic backtracking
    #also expensive as it is compiled each time
    url_pattern = re.compile(
        r'<(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)>'
    )
    url_list = url_pattern.findall(text)
    logging_wrapper("Milestone", logging.DEBUG, function="extract_url_list", msg="extraction complete", url_list=url_list)
    return url_list if len(url_list)>0 else None


def augment_user_message(user_message, url_list):
    logging_wrapper("Milestone", logging.DEBUG, function="augment_user_message", url_list=url_list)
    all_url_content = ''
    for url in url_list:
        logging_wrapper("Milestone", logging.DEBUG, function="augment_user_message", msg='fetching url', url=url)
        downloaded = fetch_url(url)
        url_content = extract(downloaded, config=newconfig)
        user_message = user_message.replace(f'<{url}>', '')
        all_url_content = all_url_content + f' Contents of {url} : \n """ {url_content} """'
    user_message = user_message + "\n" + all_url_content
    return user_message

# From https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
def num_tokens_from_messages(messages, model="gpt-4"):
    """Returns the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print("Warning: model not found. Using cl100k_base encoding.")
        encoding = tiktoken.get_encoding("cl100k_base")
    if model == "gpt-3.5-turbo" or model == "gpt-3.5-turbo-16k":
        print("Warning: gpt-3.5-turbo may change over time. Returning num tokens assuming gpt-3.5-turbo-0301.")
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0301")
    elif model == "gpt-4":
        print("Warning: gpt-4 may change over time. Returning num tokens assuming gpt-4-0314.")
        return num_tokens_from_messages(messages, model="gpt-4-0314")
    elif model == "gpt-3.5-turbo-0301":
        tokens_per_message = 4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        tokens_per_name = -1  # if there's a name, the role is omitted
    elif model == "gpt-4-0314":
        tokens_per_message = 3
        tokens_per_name = 1
    else:
        raise NotImplementedError(f"""num_tokens_from_messages() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens.""")
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens

def process_conversation_history(conversation_history, bot_user_id):
    logging_wrapper("Milestone", logging.DEBUG, function="process_conversation_history")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for message in conversation_history['messages'][:-1]:
        logging_wrapper("Milestone", logging.DEBUG, function="process_conversation_history", msg=message)
        role = "assistant" if message['user'] == bot_user_id else "user"
        message_text = process_message(message, bot_user_id)
        logging_wrapper("Milestone", logging.DEBUG, function="process_conversation_history", message_text=message_text)
        if message_text:
            messages.append({"role": role, "content": message_text})
    return messages


def process_message(message, bot_user_id):
    logging_wrapper("Milestone", logging.DEBUG, function="process_message", msg=message)
    #is it possible for this field to not be there?
    if 'text' not in message:
        logging_wrapper("Milestone", logging.DEBUG, function="process_message", msg="key 'text' not in message")

    message_text = message['text']
    role = "assistant" if message['user'] == bot_user_id else "user"
    logging_wrapper("Milestone", logging.DEBUG, function="process_message", role=role)
    if role == "user":
        url_list = extract_url_list(message_text)
        if url_list:
            message_text = augment_user_message(message_text, url_list)
    message_text = clean_message_text(message_text, role, bot_user_id)
    return message_text


def clean_message_text(message_text, role, bot_user_id):
    logging_wrapper("Milestone", logging.DEBUG, function="clean_message_text")
    if (f'<@{bot_user_id}>' in message_text) or (role == "assistant"):
        message_text = message_text.replace(f'<@{bot_user_id}>', '').strip()
        return message_text
    return None


def update_chat(app, channel_id, reply_message_ts, response_text):
    app.client.chat_update(
        channel=channel_id,
        ts=reply_message_ts,
        text=response_text
    )

