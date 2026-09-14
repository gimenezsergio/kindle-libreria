from __future__ import annotations

import unittest

from biblioteca_kindle.companion_actions import get_companion_action, list_companion_actions


class CompanionActionsTests(unittest.TestCase):
    def test_catalog_keeps_five_primary_recipes_and_grouped_extensions(self) -> None:
        actions = list_companion_actions()

        self.assertEqual(
            [action["id"] for action in actions if action["is_primary"]],
            [
                "explain-selection",
                "detect-themes",
                "explore-symbols",
                "propose-questions",
                "relate-library",
            ],
        )
        self.assertEqual(
            {action["group"] for action in actions},
            {"Comprender", "Interpretar", "Cuestionar", "Relacionar", "Recordar"},
        )
        self.assertEqual(sum(action["is_primary"] for action in actions), 5)
        self.assertEqual(len({action["id"] for action in actions}), len(actions))
        for action in actions:
            with self.subTest(action=action["id"]):
                self.assertTrue(action["label"])
                self.assertTrue(action["description"])
                self.assertTrue(action["message_template"])
                self.assertIn("material", action["requirements"])
                self.assertIn("library_search", action["requirements"])
                self.assertIn(action["search_behavior"], {"preserve", "enable"})

        relations = [action for action in actions if action["group"] == "Relacionar"]
        self.assertGreaterEqual(len(relations), 5)
        self.assertTrue(all(action["search_behavior"] == "enable" for action in relations))
        self.assertNotIn("deepseek", " ".join(action["message_template"] for action in actions).lower())

    def test_lookup_is_exact_and_rejects_unknown_actions(self) -> None:
        self.assertIsNone(get_companion_action(None))
        self.assertEqual(get_companion_action("explore-symbols").label, "Explorar símbolos")
        with self.assertRaisesRegex(ValueError, "acción"):
            get_companion_action("inventada")
        with self.assertRaisesRegex(ValueError, "acción"):
            get_companion_action(3)
