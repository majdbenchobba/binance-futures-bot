import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paper_run import build_argument_parser, build_env_updates


class PaperRunTest(unittest.TestCase):
    def test_build_env_updates_for_paper_run(self):
        parser = build_argument_parser()
        args = parser.parse_args(
            [
                "--cycles",
                "4",
                "--sleep-seconds",
                "2",
                "--symbol-allowlist",
                "ETHUSDT,BTCUSDT",
                "--max-symbol-scan",
                "2",
                "--journal-file",
                "runtime/test-paper-run.jsonl",
                "--state-file",
                "runtime/test-paper-run-state.json",
            ]
        )

        env_updates = build_env_updates(args)
        self.assertEqual(env_updates["DRY_RUN"], "true")
        self.assertEqual(env_updates["USE_TESTNET"], "true")
        self.assertEqual(env_updates["RUN_ONCE"], "false")
        self.assertEqual(env_updates["SYMBOL_ALLOWLIST"], "ETHUSDT,BTCUSDT")
        self.assertEqual(env_updates["MAX_SYMBOL_SCAN"], "2")
        self.assertEqual(env_updates["JOURNAL_FILE"], "runtime/test-paper-run.jsonl")
        self.assertEqual(env_updates["STATE_FILE"], "runtime/test-paper-run-state.json")


if __name__ == "__main__":
    unittest.main()
