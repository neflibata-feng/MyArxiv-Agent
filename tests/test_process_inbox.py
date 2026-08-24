import os
import sys
import tempfile
import unittest


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from process_inbox import append_to_papers_archive  # noqa: E402


class ProcessInboxTests(unittest.TestCase):
    def test_archive_append_is_idempotent_by_arxiv_id(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {}
            first = append_to_papers_archive(
                config,
                directory,
                "cs.AI",
                "Example",
                "https://arxiv.org/abs/2608.12345v1",
                "2026-08-24",
            )
            second = append_to_papers_archive(
                config,
                directory,
                "cs.AI",
                "Example updated",
                "https://arxiv.org/abs/2608.12345v2",
                "2026-08-25",
            )
            list_path = os.path.join(directory, "cs.AI", "List.md")
            with open(list_path, "r", encoding="utf-8") as file:
                content = file.read()

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(content.count("arxiv.org/abs/2608.12345"), 1)


if __name__ == "__main__":
    unittest.main()
