import os
import unittest
from unittest.mock import patch

from settings import GEMINI_MODEL, require_gemini_api_key


class GeminiSettingsTests(unittest.TestCase):
    def test_configures_the_initial_gemini_model(self) -> None:
        self.assertEqual(GEMINI_MODEL, "gemini-3.1-flash-lite")

    def test_requires_an_api_key_for_gemini_requests(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaisesRegex(
                RuntimeError,
                "GEMINI_API_KEY is required for Gemini requests.",
            ):
                require_gemini_api_key()

    def test_reads_api_key_from_server_environment(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            self.assertEqual(require_gemini_api_key(), "test-key")


if __name__ == "__main__":
    unittest.main()
