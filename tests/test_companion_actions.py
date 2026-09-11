from __future__ import annotations

import unittest

from biblioteca_kindle.companion_actions import list_companion_actions


class CompanionActionsTests(unittest.TestCase):
    def test_initial_catalog_has_five_provider_neutral_editable_recipes(self) -> None:
        actions = list_companion_actions()

        self.assertEqual(
            [action["id"] for action in actions],
            [
                "explain-selection",
                "detect-themes",
                "explore-symbols",
                "propose-questions",
                "relate-library",
            ],
        )
        for action in actions:
            with self.subTest(action=action["id"]):
                self.assertTrue(action["label"])
                self.assertTrue(action["description"])
                self.assertTrue(action["message_template"])
                self.assertIn("material", action["requirements"])
                self.assertIn("library_search", action["requirements"])

        relation = actions[-1]
        self.assertIn("activar", relation["requirements"]["library_search"])
        self.assertNotIn("deepseek", " ".join(action["message_template"] for action in actions).lower())
