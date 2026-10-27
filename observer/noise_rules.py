"""Rule-based noise filter. Cheap, deterministic, every rule has a name shown on the dashboard.

Rules deliberately do NOT cover things that need judgement (e.g. swapping one word for another,
which could be generic rewording or a new partner name); those go on to the LLM. Numbers are guarded: a change in any number (price, headcount, amount)
is never treated as noise by the pair rules.
"""
import re
from difflib import SequenceMatcher

COPYRIGHT = re.compile(r"©|&copy;|\(c\)|copyright|all rights reserved", re.I)
LAST_UPDATED = re.compile(r"\b(last\s+updated|updated\s+on|last\s+modified)\b", re.I)
COOKIE = re.compile(r"\bcookies?\b|\bconsent\b", re.I)
NUMBER = re.compile(r"\d[\d,.]*")
MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
DATETIME = re.compile(
    r"\d{4}-\d{2}-\d{2}|\d{1,2}[/.]\d{1,2}[/.]\d{2,4}|\d{1,2}:\d{2}(?::\d{2})?"
    rf"|{MONTHS}\.?\s+\d{{1,2}}(?:,?\s+\d{{4}})?|\d{{1,2}}\s+{MONTHS}(?:\s+\d{{4}})?|{MONTHS}\s+\d{{4}}",
    re.I)
TYPO_WORD_RATIO = 0.8      # a changed word must be this similar to its old form to count as a typo fix

BOILERPLATE_RULES = {
    "banner": "cookie_banner",
    "nav": "navigation_change",
    "script": "tracking_script",
    "style": "styling_change",
    "noscript": "tracking_script",
    "form": "form_change",
    "iframe": "embed_change",
    "svg": "icon_change",
}


def classify_boilerplate(entry):
    """entry is 'kind: text' from the cleaner. Returns a rule name."""
    kind, _, text = entry.partition(": ")
    if kind == "footer":
        return "copyright_year" if COPYRIGHT.search(text) else "footer_change"
    return BOILERPLATE_RULES.get(kind, f"{kind}_change")


def classify_block(text):
    """Single-block rules for content that survived the cleaner. Returns a rule name or None."""
    if COPYRIGHT.search(text):
        return "copyright_year"
    if LAST_UPDATED.search(text):
        return "last_updated_date"
    if COOKIE.search(text):
        return "cookie_text"
    return None


def classify_pair(old, new):
    """Rules for a block edited in place. Returns a rule name or None."""
    if DATETIME.sub("<D>", old.lower()) == DATETIME.sub("<D>", new.lower()):
        return "timestamp_only"
    if NUMBER.findall(old) != NUMBER.findall(new):
        return None                      # a changed number is never noise
    squash = lambda s: re.sub(r"[\W_]+", "", s.lower())
    if squash(old) == squash(new):
        return "formatting_only"
    old_words, new_words = old.lower().split(), new.lower().split()
    if len(old_words) == len(new_words) and all(
            a == b or SequenceMatcher(a=a, b=b).ratio() >= TYPO_WORD_RATIO
            for a, b in zip(old_words, new_words)):
        return "typo_fix"            # same words, only spelling-level edits; a swapped word is NOT noise
    return None


def filter_noise(diff):
    """Returns (added, removed, ignored). added/removed are what is left for the LLM;
    ignored is a list of {'text', 'rule'}."""
    ignored, dropped = [], set()
    for old, new in diff["pairs"]:
        rule = classify_pair(old, new)
        if rule:
            dropped.update([("r", old), ("a", new)])
            ignored.append({"text": f"{old}  ->  {new}", "rule": rule})

    added, removed = [], []
    for side, blocks, keep in (("a", diff["added"], added), ("r", diff["removed"], removed)):
        for text in blocks:
            if (side, text) in dropped:
                continue
            rule = classify_block(text)
            if rule:
                ignored.append({"text": text, "rule": rule})
            else:
                keep.append(text)
    return added, removed, ignored
