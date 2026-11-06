"""Regression tests for consequential office-title exceptions."""

import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location("position_tiers", Path(__file__).with_name("02_position_tiers.py"))
tiers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tiers)


class PresidentialSecretaryTests(unittest.TestCase):
    def test_presidential_secretaries_are_high_offices(self):
        titles = [
            "private secretary to president of Mexico",
            "Private secretary to the president",
            "Private secretary of the president of the republic",
            "private secretary to President Miguel Aleman",
            "private secretary to President de la Madrid",
            "private secretary to President Lazaro Cardenaso",
            "private secretary to President Luis Echeverria, assistant secretary, Secretariat of the Presidency",
            "personal secretary to Pres. Gustavo Diaz Ordaz",
        ]
        for title in titles:
            with self.subTest(title=title):
                rule, ranks = tiers.govt_rule(tiers.norm(title), "other")
                self.assertEqual(rule, "president_private_secretary")
                self.assertEqual(ranks[0], 4)
                self.assertIsNone(ranks[1])  # Do not invent a Smith classification.

    def test_other_secretaries_and_auxiliaries_stay_staff(self):
        titles = [
            "private secretary to president of CEN of PRI, Carlos Sansores Perez",
            "private secretary to the president of the PRI",
            "private secretary to president of Gran Comision of the Chamber of Deputies",
            "private secretary to president, Supreme Court",
            "private secretary to president, CEN of PRI",
            "private secretary to the private secretary of the president of Mexico",
            "auxiliary secretary to private secretary to President Luis Echeverria",
            "private secretary to director general of pensions",
            "private secretary to President Lazaro Cardenas during the presidential campaign",
        ]
        for title in titles:
            with self.subTest(title=title):
                rule, ranks = tiers.govt_rule(tiers.norm(title), "other")
                self.assertEqual(rule, "staff")
                self.assertEqual(ranks[0], 11)

    def test_ordinary_secretary_of_interior_stays_cabinet(self):
        self.assertEqual(
            tiers.govt_rule(tiers.norm("Secretary of the Interior"), "secretary"),
            ("cabinet_secretary", (4, 8, 9)),
        )


class InterimGovernorTests(unittest.TestCase):
    def test_actual_incumbents_do_not_depend_on_parsed_title_family(self):
        for title in ["Interim governor, Michoacan", "Provisional governor, Puebla",
                      "Substitute governor of Guerrero", "Acting governor, Sonora"]:
            with self.subTest(title=title):
                text = tiers.norm(title)
                self.assertEqual(tiers.govt_rule(text, "other"), ("governor", "GOV"))
                self.assertEqual(tiers.public_rule(text, "Other"), ("governor", "GOV"))

    def test_federal_district_is_not_a_state_governorship(self):
        self.assertEqual(tiers.govt_rule("interim governor of the federal district", "other"),
                         ("df_regent", (4, 8, 9)))

    def test_staff_candidates_and_former_governors_are_not_incumbents(self):
        for title in ["private secretary to interim governor, Puebla",
                      "candidate for interim governor, Puebla",
                      "former interim governor, Puebla"]:
            with self.subTest(title=title):
                rule, value = tiers.govt_rule(title, "other")
                self.assertNotEqual(value, "GOV")


class ExplicitOfficeTextTests(unittest.TestCase):
    def test_missing_parsed_title_does_not_hide_a_senator(self):
        for title in ["senator from Tabasco, 1988-1994", "Federal senator from Hidalgo"]:
            with self.subTest(title=title):
                self.assertEqual(tiers.public_rule(tiers.norm(title), "nan"),
                                 ("senator", (6, 3, None)))

    def test_alternates_and_candidates_are_not_automatically_incumbents(self):
        for title in ["Alternate senator from Tabasco", "candidate for senator from Hidalgo"]:
            with self.subTest(title=title):
                self.assertNotEqual(tiers.public_rule(tiers.norm(title), "nan")[0], "senator")

    def test_supreme_court_title_variants_have_the_historical_court_rank(self):
        for title in ["justice, Supreme Court", "president, Supreme Court of Justice",
                      "president, Supreme Court of Mexico", "Supreme Court justice"]:
            with self.subTest(title=title):
                self.assertEqual(tiers.govt_rule(tiers.norm(title), "other"),
                                 ("supreme_court_justice", (6, None, None)))

    def test_state_supreme_court_and_aide_are_distinguished(self):
        self.assertEqual(tiers.govt_rule(tiers.norm("justice, State Supreme Court, Jalisco"), "justice"),
                         ("state_judge", (10, None, None)))
        self.assertEqual(tiers.govt_rule(tiers.norm("private secretary to president, Supreme Court"), "other")[0],
                         "staff")


class ChiefOfStaffScopeTests(unittest.TestCase):
    def test_national_military_and_presidential_titles_keep_high_rank(self):
        for title in ["chief of staff, Secretariat of National Defense",
                      "chief of staff of navy", "Chief of staff, air force",
                      "presidential chief of staff", "chief of presidential staff",
                      "chief of staff for Pres. Gustavo Diaz Ordaz",
                      "chief of staff, President Emilio Portes Gil",
                      "chief of staff, Office of the Presidency"]:
            with self.subTest(title=title):
                self.assertEqual(tiers.govt_rule(tiers.norm(title), "other"),
                                 ("presidential_chief_of_staff", (4, 4, 8)))

    def test_staff_of_other_officials_do_not_inherit_national_chief_rank(self):
        for title in ["chief of staff of director general, Bank of Mexico, Miguel Mancera",
                      "chief of staff for assistant secretary of media relations, Secretariat of Government",
                      "chief of staff, Mexican ambassador to the United States",
                      "chief of staff to secretary of foreign relations",
                      "chief of staff of assistant secretary, Secretariat of National Defense"]:
            with self.subTest(title=title):
                self.assertEqual(tiers.govt_rule(tiers.norm(title), "head"),
                                 ("staff_chief_scope_unresolved", None))


if __name__ == "__main__":
    unittest.main()
