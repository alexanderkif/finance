import unittest

from core.playbook_registry import load_playbooks


class PlaybookRegistryTests(unittest.TestCase):
    def test_loads_all_eight_valid_playbooks(self) -> None:
        playbooks = load_playbooks()

        self.assertEqual(
            set(playbooks),
            {
                "bull_put_spread",
                "bear_call_spread",
                "bull_call_spread",
                "bear_put_spread",
                "long_call",
                "long_put",
                "short_call",
                "short_put",
            },
        )
        self.assertEqual(playbooks["bull_put_spread"].leg_count, 2)
        self.assertEqual(
            playbooks["bull_put_spread"].loss_formula,
            "Strike width - net credit per share",
        )
        self.assertEqual(playbooks["short_call"].loss_formula, "Unlimited")
        for playbook in playbooks.values():
            self.assertEqual(
                set(playbook.event_sensitivity),
                {"earnings", "dividends", "macro"},
            )
