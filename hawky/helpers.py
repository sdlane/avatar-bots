import random

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
