"""Verify extracted figures against source text without a model."""
import json
import re
from decimal import Decimal

from .costs import CACHE_DIR, write_json
from .extract import cache_path, parse_args, selected_articles

PUNCTUATION = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2212": "-", "\u202f": " ", "\u2009": " ",
})
SCALES = {
    "k": 3, "thousand": 3, "m": 6, "mn": 6, "million": 6,
    "b": 9, "bn": 9, "billion": 9, "tn": 12, "trillion": 12,
}
FIGURE = re.compile(
    r"(?<![\w.,])(?P<sign>[+-])?(?:(?P<currency>US\$|[$\u20ac\u00a3]|USD|EUR|GBP)\s*)?"
    r"(?P<amount>[+-]?(?:\d{1,3}(?:[ '\u00a0]\d{3})+|\d+)(?:[.,]\d+)*|[.,]\d+)"
    r"(?:\s*(?P<scale>thousand|million|billion|trillion|mn|bn|tn|[kmb])\b)?"
    r"(?:\s*(?P<unit>%|(?:percent|per cent|bps?|basis points?)\b))?"
    r"(?!\w|[.,]\d)", re.IGNORECASE,
)
CURRENCIES = {"$": "usd", "us$": "usd", "\u20ac": "eur", "\u00a3": "gbp"}


NUMBER_WORD = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"hundred|thousand|million|billion|half|double)\b", re.IGNORECASE,
)


def normalize_text(value):
    return " ".join(value.translate(PUNCTUATION).split())


def normalize_amount(raw):
    raw = raw.replace(" ", "").replace("'", "")
    if "," in raw and "." in raw:
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        return Decimal(raw.replace(thousands, "").replace(decimal, "."))
    separator = "," if "," in raw else "."
    groups = raw.lstrip("+-").split(separator)
    # English sources conventionally use commas for thousands. Repeated dots
    # with groups of three are also accepted as thousands separators.
    grouped = (
        len(groups) > 1 and 0 < len(groups[0]) <= 3
        and int(groups[0]) != 0 and all(len(group) == 3 for group in groups[1:])
        and (separator == "," or len(groups) > 2)
    )
    if grouped:
        return Decimal(raw.replace(separator, ""))
    whole, found, fraction = raw.rpartition(separator)
    return Decimal(whole.replace(separator, "") + "." + fraction if found else raw)


def normalized_figures(value):
    for match in FIGURE.finditer(normalize_text(value)):
        sign, currency, amount, scale, unit = match.groups("")
        number = normalize_amount(sign + amount).scaleb(SCALES.get(scale.lower(), 0))
        currency = CURRENCIES.get(currency.lower(), currency.lower())
        unit = unit.lower()
        if unit:
            unit = "bps" if unit.startswith(("bp", "basis")) else "%"
        yield number, unit, currency


def is_word_figure(value):
    return not any(char.isdecimal() for char in value) and NUMBER_WORD.search(value) is not None


def rejection_reason(figure, source):
    phrase = normalize_text(figure["phrase"])
    if not phrase or phrase not in source:
        return "phrase_not_found"
    value = normalize_text(figure["value_text"])
    if is_word_figure(value):
        if re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", phrase, re.IGNORECASE):
            return None
        return "value_not_found_in_phrase"
    expected = list(normalized_figures(value))
    if not expected:
        return "value_not_numeric"
    # Require a contiguous match for compound figures such as numeric ranges.
    if len(expected) > 1 and re.search(
        r"(?<![\w.,+\-$\u20ac\u00a3])" + re.escape(value) + r"(?!\w|[.,]\d)", phrase
    ):
        return None
    if len(expected) == 1:
        number, unit, currency = expected[0]
        for candidate, candidate_unit, candidate_currency in normalized_figures(phrase):
            if (candidate == number and candidate_unit == unit
                    and (not currency or not candidate_currency or currency == candidate_currency)):
                return None
    return "value_not_found_in_phrase"


def main():
    args = parse_args(__doc__)
    articles = selected_articles(args.date, args.limit, args.overnight)
    verified, rejected = [], []
    examples = []
    for article in articles.itertuples(index=False):
        path = cache_path(article.id)
        if not path.exists():
            raise SystemExit(f"Missing extraction for {article.id}. Run src.extract first.")
        extraction = json.loads(path.read_text(encoding="utf-8"))
        metadata = {
            "article_id": article.id, "outlet": article.outlet, "headline": article.headline,
            "link": article.link, "topic": extraction["topic"], "summary": extraction["summary"],
        }
        source = normalize_text(article.text)
        for figure in extraction["figures"]:
            record = {**metadata, **figure}
            reason = rejection_reason(figure, source)
            if reason:
                rejected.append({**record, "reason": reason})
                if len(examples) < 5:
                    phrase = normalize_text(figure["phrase"])
                    if source and source in phrase:
                        phrase = "[omitted: full article]"
                    examples.append((figure["value_text"][:80], reason, phrase[:200]))
            else:
                if is_word_figure(normalize_text(figure["value_text"])):
                    record["kind"] = "word"
                verified.append(record)

    write_json(CACHE_DIR / "verified.json", verified)
    write_json(CACHE_DIR / "rejected.json", rejected)
    total = len(verified) + len(rejected)
    rate = len(verified) / total if total else 0
    print(f"Figures: {total} | Verified: {len(verified)} | Rejected: {len(rejected)} | Verified: {rate:.1%}")
    for value, reason, phrase in examples:
        print(json.dumps({"value_text": value, "reason": reason, "phrase": phrase}))


if __name__ == "__main__":
    main()
