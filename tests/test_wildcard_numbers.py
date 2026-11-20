import unittest

from src.script import Sentence, numeric_mentions, sentence_errors, word_windows
from src.wildcard_checks import advisory, introduction


class WildcardReceiptTests(unittest.TestCase):
    def period_errors(self, language, text, measure):
        facts = {"F1": {"fact_id": "F1", "value_text": "0.54%", "measures": measure}}
        return {e["motivo"] for e in sentence_errors(Sentence(text=text, fact_ids=["F1"]), facts, set(),
                                                    listener="wildcard-test", language=language)}

    def test_period_must_match_spoken_receipt(self):
        for language, wrong, correct, measure in [
            ("de", "Der Index stieg um 0,54 Prozent.", "Über fünf Tage stieg der Index um 0,54 Prozent.", "gain over five days"),
            ("de", "Der Index stieg um 0,54 Prozent. Die vergangenen fünf Tage waren ruhig.",
             "Über fünf Tage stieg der Index um 0,54 Prozent.", "gain over five days"),
            ("nl", "De index steeg in zes dagen met 0,54 %.", "De index steeg in vijf dagen met 0,54 %.", "gain over five days"),
            ("en", "The index fell today by 0.54%.", "The index fell over the past week by 0.54%.", "decline over the past week"),
            ("de", "Im letzten Jahr stieg er um 0,54 Prozent.", "Seit Jahresbeginn stieg er um 0,54 Prozent.", "year-to-date gain"),
            ("en", "Revenue grew 0.54%.", "Revenue grew 0.54% this year.", "this year's growth"),
            ("nl", "De omzet steeg met 0,54 %.", "De kwartaalomzet steeg met 0,54 %.", "quarterly revenue growth"),
            ("de", "Im dritten Quartal stieg sie um 0,54 %.", "Im 4. Quartal stieg sie um 0,54 %.", "fourth-quarter revenue growth"),
        ]:
            with self.subTest(language=language, measure=measure):
                self.assertIn("missing_or_wrong_measure_period", self.period_errors(language, wrong, measure))
                self.assertFalse(self.period_errors(language, correct, measure))
        self.assertIn("number_not_in_cited_facts", self.period_errors(
            "nl", "De index steeg in vijf dagen met 0,54 % en zes euro.", "gain over five days"))

    def test_trade_advice_and_buyer_predictions(self):
        for language, lines in {
            "en": ["Investors should wait.", "You ought to act.", "Consider buying or selling.", "Hold the stock.",
                   "At that price buyers could return."],
            "de": ["Exporteure sollten anders kalkulieren.", "Ein Händler sollte warten.", "Wir empfehlen Zurückhaltung.",
                   "Bei diesem Kurs könnten Käufer wieder einsteigen."],
            "nl": ["Je zou moeten wachten.", "Bedrijven zouden voorzichtig moeten zijn.", "Wij raden beleggers aan te wachten.",
                   "Een koers waar kopers mogelijk terugkomen."],
        }.items():
            for line in lines:
                with self.subTest(line=line):
                    self.assertTrue(advisory(line, language))
        self.assertFalse(advisory("Dat maakt geïmporteerde goederen duurder.", "nl"))

    def test_production_sentences(self):
        self.assertEqual(introduction("Sam", "en"), ["Good morning, Sam.", "An AI voice reads this briefing."])
        self.assertEqual(introduction("Lena", "de"), ["Guten Morgen, Lena.", "Diese Nachrichten liest eine KI-Stimme."])
        self.assertEqual(introduction("Noor", "nl"), ["Goedemorgen, Noor.", "Een AI-stem leest dit nieuws voor."])

    def errors(self, text, value, language, unit="", source=""):
        fact = {"fact_id": "F001", "article_id": "a", "value_text": value, "unit": unit}
        line = Sentence(text=text, story_id="s", fact_ids=["F001"])
        return {e["motivo"] for e in sentence_errors(
            line, {"F001": fact}, set(word_windows(source)), language=language)}

    def test_local_printed_values_match_english_receipts(self):
        for language, printed, source, unit in [
            ("de", "3,6 %", "3.6%", "percent"),
            ("de", "5 Prozent", "5 per cent", "percent"),
            ("de", "3,2 Billionen Euro", "EUR 3.2 trillion", "EUR"),
            ("de", "34 US-Cent", "34 cents", "US cents per share"),
            ("nl", "2,1 biljoen dollar", "$2.1 trillion", "USD"),
            ("nl", "64.620 dollar", "$64,620", "USD"),
            ("nl", "1,25 procent", "1.25%", "percent"),
            ("nl", "25 basispunten", "25 basis points", "bps"),
        ]:
            with self.subTest(printed=printed):
                text = "Index: " + printed
                self.assertEqual([raw for raw, _ in numeric_mentions(text, language)], [printed])
                self.assertFalse(self.errors(text, source, language, unit))

    def test_wrong_scale_currency_and_unverified_words_are_blocked(self):
        for text, source, language in [
            ("Wert: 3 Billionen Euro", "EUR 3 billion", "de"),
            ("Prijs: 64.620 euro", "$64,620", "nl"),
            ("Groei: 3,6 procentpunt", "3.6%", "nl"),
            ("Wert: neunundvierzig", "4", "de"),
        ]:
            with self.subTest(text=text):
                self.assertIn("number_not_in_cited_facts", self.errors(text, source, language))

    def test_existing_sentence_limits_and_copy_rule(self):
        text = "De index lag volgens de bank hoger dan verwacht."
        self.assertIn("copied_sequence_of_8_words", self.errors(text, "4", "nl", source=text))
        self.assertIn("more_than_two_numbers", self.errors("Wert: 2, 3 und 4", "4", "de"))
        self.assertIn("repeated_number", self.errors("Prijs: 2 euro, opnieuw 2 euro", "EUR 2", "nl"))
