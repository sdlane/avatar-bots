import random
import re

emote_texts = ["\"The stomach is the source of energy in your body. It is called the Sea of Chi. Only in my case, it is more like a vast ocean.\"",
               "\"Are you so busy fighting you cannot see your own ship has set sail?\"",
               "\"You should rest. A man needs his rest.\"",
               "\"The Fire Nation needs the moon too. We all depend on the balance.\"",
               "\"This tea is nothing more than hot leaf juice!\"",
               "\"There is nothing wrong with letting people who love you help you.\"",
               "\"Many things that seem threatening in the dark becoome welcoming when we shine light on them.\"",
               "\"The best tea tastes delicious whether it comes in a porcelain pot or a tin cup.\"",
               "\"Follow your passion and life will reward you.\"",
               "\"The only thing better than finding something you're looking for is finding something you weren't looking for at a great bargain!\"",
               "\"Today, destiny is our friend. I know it.\"",
               "\"There is nothing wrong with a life of peace and prosperity. I suggest you think about what it is that you want from your life and why.\"",
               "\"At my age, there is only one big surprise left, and I'd just as soon leave it a mystery.\"",
               "\"A moment of quiet is good for your mental well-being.\"",
               "\"Sometimes, the best way to solve your own problems is to help someone else.\"",
               "\"Be careful what you wish for. History is not always kind to its subjects.\"",
               "\"Perfection and power are overrated. I think you are very wise to choose happiness and love.\"",
               "\"It is usually best to admit mistakes when they occur, and to seek to restore honor.\"",
               "\"It is important to draw wisdom from many different places.\"",
               "\"It's time for you to look inward and start asking yourself the big questions: Who are you, and what do you want?\"",
               "\"If you look for the dark, that is all you will ever see.\"",
               "\"Sharing tea with a fascinating stranger is one of life's true delights.\"",
               "\"In the darkest times, hope is something you give yourself. That is the meaning of inner strength.\"",
               "\"Sometimes, life is like this dark tunnel. You can't always see the light at the end of the tunnel, but if you just keep moving you will come to a better place.\"",
               "\"Destiny is a funny thing. You never know how things are going to work out.\"",
               "\"While it is always great to believe in oneself, a little help from others can be a great blessing.\"",
               "\"Pride is not the opposite of shame, but its source. True humility is the only antidote to shame.\"",
               "\"Life happens wherever you are, whether you make it or not.\"",
               "\"Leaves from the vine\nFalling so slow\nLike fragile tiny shells\nDrifting in the foam\nLittle soldier boy\nCome marching home\nBrave soldier boy\nComes marching home\""]

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
