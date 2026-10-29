import os
import unittest
from unittest.mock import patch

from settings import (
    GEMINI_MODEL,
    require_finnhub_api_key,
    require_gemini_api_key,
    require_twelve_data_api_key,
)


class GeminiSettingsTests(unittest.TestCase):
    def test_configures_the_initial_gemini_model(self) -> None:
        self.assertEqual(GEMINI_MODEL, "gemini-3.1-flash-lite")

    def test_requires_an_api_key_for_gemini_requests(self) -> None:
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": ""}),
            self.assertRaisesRegex(
                RuntimeError,
                "GEMINI_API_KEY is required for Gemini requests.",
            ),
        ):
            require_gemini_api_key()

    def test_reads_api_key_from_server_environment(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            self.assertEqual(require_gemini_api_key(), "test-key")

    def test_requires_candle_provider_key(self) -> None:
        with (
            patch.dict(os.environ, {"TWELVE_DATA_API_KEY": ""}),
            self.assertRaisesRegex(RuntimeError, "TWELVE_DATA_API_KEY"),
        ):
            require_twelve_data_api_key()

    def test_requires_news_provider_key(self) -> None:
        with (
            patch.dict(os.environ, {"FINNHUB_API_KEY": ""}),
            self.assertRaisesRegex(RuntimeError, "FINNHUB_API_KEY"),
        ):
            require_finnhub_api_key()


if __name__ == "__main__":
    unittest.main()
