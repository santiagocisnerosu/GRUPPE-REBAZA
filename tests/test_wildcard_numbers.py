import unittest

from src.script import Sentence, numeric_mentions, sentence_errors, word_windows


class WildcardReceiptTests(unittest.TestCase):
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
