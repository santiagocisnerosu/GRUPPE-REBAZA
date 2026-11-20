"""Classify evidenced numeric and copying failures for the public player."""
import re
from difflib import SequenceMatcher

from .script import authorized_numbers, matches_number, numeric_mentions, spoken_citations


def classify_caught(issues, script, verified):
    language = script.get("language", "en")
    available = [number for fact in verified for number in authorized_numbers(fact, language)]
    final_spoken = list(spoken_citations(script))
    classified = {}
    for issue in issues:
        reason = issue["motivo"]
        sentence = issue.get("frase_evaluada", issue["frase_original"])
        raw = issue.get("cifra")
        if reason == "copied_sequence_of_8_words":
            kind = "copied"
        elif reason == "number_not_in_cited_facts" and raw:
            mentions = [actual for label, actual in numeric_mentions(sentence, language) if label == raw]
            if not mentions:
                continue
            values = [value for value in mentions if value is not None]
            if not values:
                # Spelled-out quantities can be formatted incorrectly without being invented.
                values = authorized_numbers({"value_text": raw}, language)
            if not values:
                continue
            in_ledger = any(matches_number(known, value) for known in available for value in values)
            if not in_ledger:
                kind = "invented"
            else:
                original_sources = set(issue.get("original_article_ids", []))
                correction = next((
                    (facts, accepted) for _, facts, accepted in final_spoken
                    if SequenceMatcher(None, sentence.casefold(), accepted.casefold()).ratio() >= .55
                    and any(matches_number(known, value) for fact in facts
                            for known in authorized_numbers(fact, language) for value in values)
                    and (
                        any(fact["article_id"] not in original_sources for fact in facts)
                        if original_sources else accepted != sentence
                    )
                ), None)
                # A verified value dropped from the final script is not a citation fix.
                if correction is None:
                    continue
                kind = "miscited"
        else:
            continue
        result = {**issue, "kind": kind}
        if kind == "miscited":
            facts, accepted = correction
            result["correction"] = accepted
            result["source_article_ids"] = sorted({fact["article_id"] for fact in facts})
        classified.setdefault((kind, raw, re.sub(r"\s+", " ", sentence).casefold()), result)
    return list(classified.values())
