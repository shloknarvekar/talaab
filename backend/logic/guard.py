"""Number guard: the AI may only use numbers that exist in our data.

invented_numbers(text, doc) returns every number in the text that cannot be traced to the
ponds.json document. Allowed besides the document's own numbers: calendar day numbers
(1-31, so dates can be written out) and the method's fixed rules (5% dry line, 30/90-day
status bands, 45-day window, 2x flag threshold). Devanagari digits are normalised first.
"""
from __future__ import annotations

import json
import re

NUM_RE = re.compile(r"\d+(?:\.\d+)?")
DEVANAGARI = str.maketrans("०१२३४५६७८९", "0123456789")
METHOD_CONSTANTS = {"5", "20", "30", "45", "90", "2"}


def _norm(n: str) -> str:
    """'41.0' -> '41', '8.60' -> '8.6', '003' -> '3' so formatting differences don't count."""
    if "." in n:
        n = n.rstrip("0").rstrip(".")
    return n.lstrip("0") or "0"


def numbers_in(text: str) -> set[str]:
    return {_norm(n) for n in NUM_RE.findall(text.translate(DEVANAGARI))}


def invented_numbers(text: str, doc: dict) -> set[str]:
    allowed = numbers_in(json.dumps(doc, ensure_ascii=False))
    allowed |= {str(d) for d in range(1, 32)} | METHOD_CONSTANTS
    return numbers_in(text) - allowed
