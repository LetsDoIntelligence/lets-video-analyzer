"""Turn a question's unknown noun ("trees", "traffic lights") into a search term, and back."""

import re

MAX_TERM = 30  # characters; the tracks table stores the class name in a short column

_COLOR_WORDS = {
    "white", "black", "gray", "grey", "silver", "red", "orange", "yellow", "green", "blue",
    "purple", "pink", "brown",
}  # fmt: skip
# Words that describe the noun rather than name it; dropped from the front of the phrase.
_FILLER = {
    "the", "a", "an", "any", "all", "some", "different", "unique", "distinct", "total",
    "big", "small", "large", "tall", "old", "new", "more", "many",
}  # fmt: skip
# Nouns that don't name something to look for ("how many objects").
GENERIC = {
    "objects", "object", "things", "thing", "items", "item", "times", "time", "ones", "one",
    "of", "total", "everything", "anything", "something", "them", "it", "there", "are", "were",
    "detection", "detections", "result", "results", "table", "chart", "graph", "report",
    "summary", "breakdown", "detail", "details", "data", "timestamp", "timestamps", "video",
    "footage", "scene", "frame", "frames", "minute", "minutes", "second", "seconds",
}  # fmt: skip

# Where the noun phrase ends: "how many trees are there between 0:10 and 0:40".
_STOP = re.compile(
    r"\b(are|is|were|was|do|does|did|in|on|at|between|from|during|within|over|before|after|"
    r"for|passed|pass|passing|appear\w*|there|visible|seen|with|that|which|across|"
    r"throughout|first|last|per|each|can|could|will|would|have|has|had|total|overall)\b"
)
_LEADS = [
    re.compile(r"\bhow many (.+)"),
    re.compile(
        r"\b(?:are there|is there|do you see|can you see|find|count|locate|spot|show me|list)"
        r" (.+)"
    ),
]


def singularize(word: str) -> str:
    """Good-enough English singular for the nouns people ask about."""
    irregular = {
        "people": "person",
        "persons": "person",
        "buses": "bus",
        "men": "man",
        "women": "woman",
    }
    if word in irregular:
        return irregular[word]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("sses", "shes", "ches", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")) and len(word) > 3:
        return word[:-1]
    return word


def pluralize(term: str) -> str:
    head, _, last = term.rpartition(" ")
    if last == "person":
        plural = "people"
    elif last == "bus":
        plural = "buses"
    elif last.endswith("y") and last[-2:-1] not in "aeiou":
        plural = last[:-1] + "ies"
    elif last.endswith(("s", "x", "ch", "sh")):
        plural = last + "es"
    else:
        plural = last + "s"
    return f"{head} {plural}".strip()


def normalize_term(phrase: str) -> str | None:
    """A clean singular search term, or None when the phrase doesn't name a thing."""
    words = re.sub(r"[^a-z0-9 -]", " ", phrase.lower()).split()
    while words and (words[0] in _FILLER or words[0] in _COLOR_WORDS):
        words.pop(0)
    if not words or len(words) > 3 or all(w in GENERIC for w in words):
        return None
    words[-1] = singularize(words[-1])
    term = " ".join(words)
    if len(term) > MAX_TERM or len(term) < 2 or words[-1] in GENERIC:
        return None
    return term


def extract_term(question: str) -> str | None:
    """The thing a question asks about, when it is not one of the built-in classes."""
    q = question.lower().strip().rstrip("?.! ")
    for lead in _LEADS:
        m = lead.search(q)
        if not m:
            continue
        phrase = _STOP.split(m.group(1), maxsplit=1)[0]
        return normalize_term(phrase)
    return None
