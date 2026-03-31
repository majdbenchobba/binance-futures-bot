import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from journal import append_journal_entry


class JournalTest(unittest.TestCase):
    def test_append_journal_entry_writes_jsonl_line(self):
        with TemporaryDirectory() as tmp_dir:
            journal_path = Path(tmp_dir) / "journal.jsonl"
            written = append_journal_entry(
                "cycle_summary",
                {"cycle_count": 1, "summary": "ok"},
                path=journal_path,
                enabled=True,
            )

            self.assertTrue(written)
            lines = journal_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            self.assertEqual(entry["event"], "cycle_summary")
            self.assertEqual(entry["payload"]["cycle_count"], 1)

    def test_append_journal_entry_respects_disabled_flag(self):
        with TemporaryDirectory() as tmp_dir:
            journal_path = Path(tmp_dir) / "journal.jsonl"
            written = append_journal_entry(
                "cycle_summary",
                {"cycle_count": 1},
                path=journal_path,
                enabled=False,
            )

            self.assertFalse(written)
            self.assertFalse(journal_path.exists())


if __name__ == "__main__":
    unittest.main()
