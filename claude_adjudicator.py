"""claude_adjudicator.py — the adjudicator for entity_resolver's ambiguous
match band (name similarity clears the adjudicate threshold and DOB
matches exactly or nearly, but not both confidently enough to auto-merge).

DEMO_MODE (default) uses a deterministic heuristic instead of calling the
Anthropic API: shared surname and a matching DOB are not enough on their
own (two unrelated people can share both — see README, "Anderson Senger"
vs "Shon Senger" in the demo dataset, same surname AND birthdate by
Synthea's random generation, clearly different first names). The demo
heuristic additionally requires the first names to be similar (typo/
nickname distance), which is exactly the signal a careful human reviewer
would use.

In live mode Claude sees both full records (name, DOB, gender, address)
and is asked a strict yes/no question. Claude adjudicates a match; it
never re-scores or overrides the entity_resolver's thresholds.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from config import CLAUDE_MODEL, DEMO_MODE

DEMO_FIRST_NAME_SIMILARITY_THRESHOLD = 60


def _demo_adjudicator(a: dict, b: dict) -> bool:
    fa = (a.get("first_name") or "").lower()
    fb = (b.get("first_name") or "").lower()
    if not fa or not fb:
        return False
    return SequenceMatcher(None, fa, fb).ratio() * 100 >= DEMO_FIRST_NAME_SIMILARITY_THRESHOLD


_SYSTEM_PROMPT = (
    "You are adjudicating whether two patient records from different "
    "hospital IT systems describe the same real person. Both records "
    "already passed a fuzzy name-match and a date-of-birth match. Answer "
    'with strict JSON: {"same_patient": true or false}. Two people can '
    "share a surname and even a birthdate by coincidence -- if the given "
    "names are not plausibly the same person (not a nickname, misspelling, "
    "or transcription variant of each other), answer false."
)


def _claude_adjudicator(a: dict, b: dict) -> bool:
    try:
        import json

        import anthropic
        client = anthropic.Anthropic()
        prompt = (
            f"Record A: {a.get('first_name')} {a.get('last_name')}, "
            f"DOB {a.get('dob')}, gender {a.get('gender')}\n"
            f"Record B: {b.get('first_name')} {b.get('last_name')}, "
            f"DOB {b.get('dob')}, gender {b.get('gender')}"
        )
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=50,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(msg.content[0].text.strip())
        return bool(data.get("same_patient", False))
    except Exception:
        return _demo_adjudicator(a, b)


def adjudicate(a: dict, b: dict) -> bool:
    if DEMO_MODE:
        return _demo_adjudicator(a, b)
    return _claude_adjudicator(a, b)
