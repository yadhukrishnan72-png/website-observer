"""Turn raw HTML into (a) ordered clean text blocks and (b) the boilerplate the cleaner removed.

Blocks are what we compare for meaning. Boilerplate (nav, footer, cookie banner, scripts) is kept
only so that a change there can be logged as ignored, with a reason, instead of vanishing silently.
"""
import hashlib
import re

from bs4 import BeautifulSoup

NOISE_ATTR = re.compile(r"cookie|consent|banner|popup|gdpr", re.I)
BLOCK_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "td", "th", "blockquote"]
CODE_TAGS = ["script", "style", "noscript"]
LAYOUT_TAGS = ["nav", "header", "footer", "form", "iframe", "svg"]


def _normalise(text):
    return re.sub(r"\s+", " ", text).strip()


def clean(html):
    """Returns (blocks, boilerplate). boilerplate entries look like 'footer: (c) 2025 Acme AI ...'."""
    soup = BeautifulSoup(html, "html.parser")
    boilerplate = []

    for tag in soup(CODE_TAGS):
        text = _normalise(tag.string or "") or tag.get("src") or ""
        if text:
            boilerplate.append(f"{tag.name}: {text}")
        tag.decompose()

    noisy = [el for el in soup.find_all(True)
             if NOISE_ATTR.search(" ".join(el.get("class", [])) + " " + (el.get("id") or ""))]
    for el in noisy:
        if el.decomposed:
            continue
        boilerplate.append(f"banner: {_normalise(el.get_text(' '))}")
        el.decompose()

    for tag in soup(LAYOUT_TAGS):
        if tag.decomposed:
            continue
        text = _normalise(tag.get_text(" "))
        if text:
            boilerplate.append(f"{'nav' if tag.name == 'header' else tag.name}: {text}")
        tag.decompose()

    blocks = []
    for el in soup.find_all(BLOCK_TAGS):
        if el.find(BLOCK_TAGS):          # skip containers; their children are captured separately
            continue
        text = _normalise(el.get_text(" "))
        if len(text) >= 2:
            blocks.append(text)
    return blocks, boilerplate


def content_hash(blocks):
    return hashlib.sha256("\n".join(b.lower() for b in blocks).encode("utf-8")).hexdigest()
