import random
import re

emote_texts = ["\"kreee!\"",
               "\"kyeeer!\"",
               "\"keee-EEER!\"",
               "\"keh keh keh\"",
               "\"scree\"",
               "\"grk\"",
               "*whoooosshhhhh*",
               "*screeches in hawk*",
               "*ruffles his feathers disdainfully*",
               "*whistles innocently*",
               "*tilts his head and stares*",
               "*hops excitedly*",
               "*stretches his wings*"]

def get_emote_text():
    return random.choice(emote_texts)

def emotive_message(confirm_text: str):
    return f'{get_emote_text()}\n({confirm_text})'

def remove_mention(text: str) -> str:
    """
    Remove Discord mention from the start of a string.
    Discord mentions are in the format <@USER_ID> or <@!USER_ID>
    """
    # Pattern matches <@USER_ID> or <@!USER_ID> followed by optional whitespace at the start
    pattern = r'^<@!?\d+>\s*'
    return re.sub(pattern, '', text).strip()
