"""Parse printed Dutch and German figures without losing their receipt labels."""
import re
from decimal import Decimal

SCALES = {
    "tausend": 3, "duizend": 3, "mio": 6, "mln": 6, "million": 6, "millionen": 6,
    "miljoen": 6, "miljoenen": 6, "mrd": 9, "milliarde": 9, "milliarden": 9,
    "miljard": 9, "miljarden": 9, "mld": 9, "billion": 12, "billionen": 12,
    "biljoen": 12, "biljoenen": 12, "bio": 12, "tsd": 3,
}
MONEY = r"US[- ]?Dollars?|Amerikaanse dollars?|Dollars?|Euro(?:['’]s|s)?|Pfund|pond|USD|EUR|GBP|US\$|[$€£]"
SCALE = "|".join(sorted(SCALES, key=len, reverse=True))
UNIT = r"%|Prozentpunkte?n?|procentpunt(?:en)?|Prozent|procent|Basispunkt(?:e[n]?)?|basispunt(?:en)?|bps|(?:US[- ]?|Euro[- ]?)?cents?"
ONES = {"ein", "eine", "einer", "einen", "einem", "eines", "één", "een"}
NUM = re.compile(
    rf"(?<![\w.,])(?P<sign>[+-])?(?:(?P<prefix>{MONEY})\s*)?"
    rf"(?P<amount>[+-]?(?:\d{{1,3}}(?:[. \u202f\u00a0\u2009]\d{{3}})+(?!\d)|\d+)(?:,\d+)?|"
    rf"(?:{'|'.join(sorted(ONES, key=len, reverse=True))})(?=\s+(?:{SCALE})\b))"
    rf"(?:\s*(?P<scale>{SCALE})\b\.?)?(?:\s*(?P<suffix>{MONEY})(?!\w))?"
    rf"(?:\s*(?P<unit>{UNIT})(?!\w))?(?!\w|[.,]\d)", re.I)
CARDINAL = (r"null|nul|eins|ein|één|een|zwei|drei|vier|fünf|sechs?|sieb(?:en)?|acht|neun|zehn|elf|zwölf|"
            r"zwanzig|dreißig|vierzig|fünfzig|sechzig|siebzig|achtzig|neunzig|hundert|tausend|"
            r"twee|drie|vijf|zes|zeven|negen|tien|twaalf|twintig|dertig|veertig|vijftig|zestig|"
            r"zeventig|tachtig|negentig|honderd|duizend|der|veer")
NUMBER_WORDS = re.compile(rf"\b(?:(?:{CARDINAL})(?:(?:und|en|ën)?(?:{CARDINAL}))*)\b|\b(?:{SCALE})\b|\d+", re.I)


def unmatched(fragment):
    for m in NUMBER_WORDS.finditer(fragment):
        # Unstressed indefinite articles are ubiquitous in both languages.
        if m[0].lower() not in {"ein", "een", "der", "veer"}:
            yield m[0], None


def mentions(text):
    normalized = text.translate(str.maketrans("−–‑", "---"))
    end = 0
    for match in NUM.finditer(normalized):
        yield from unmatched(text[end:match.start()])
        amount = match["amount"].lower()
        number = Decimal("1" if amount in ONES else "".join(amount.split()).replace(".", "").replace(",", "."))
        if match["sign"] == "-":
            number = -number
        number = number.scaleb(SCALES.get((match["scale"] or "").lower(), 0))
        currency = (match["prefix"] or match["suffix"] or "").lower()
        if currency:
            currency = "eur" if currency.startswith(("eur", "€")) else (
                "gbp" if currency in {"gbp", "£", "pfund", "pond"} else "usd")
        unit = (match["unit"] or "").lower()
        if unit.startswith(("basis", "bps")):
            unit = "bps"
        elif "punkt" in unit or "punt" in unit:
            unit = "pp"
        elif "cent" in unit and unit != "procent":
            currency = "usd" if unit.startswith("us") else "eur" if unit.startswith("euro") else currency
            unit = "cent"
        elif unit:
            unit = "%"
        yield text[match.start():match.end()], (number, unit, currency)
        end = match.end()
    yield from unmatched(text[end:])
