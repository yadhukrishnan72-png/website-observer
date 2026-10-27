"""Block-level diff using difflib."""
from difflib import SequenceMatcher


def diff_blocks(old, new):
    """Returns {'added': [...], 'removed': [...], 'pairs': [(old, new), ...]}.

    'pairs' are blocks that were edited in place (a replace op with equal-length sides), so the
    noise rules can judge old vs. new text. Paired blocks also appear in added/removed.
    """
    added, removed, pairs = [], [], []
    for op, i1, i2, j1, j2 in SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        removed.extend(old[i1:i2])
        added.extend(new[j1:j2])
        if op == "replace" and (i2 - i1) == (j2 - j1):
            pairs.extend(zip(old[i1:i2], new[j1:j2]))
    return {"added": added, "removed": removed, "pairs": pairs}
