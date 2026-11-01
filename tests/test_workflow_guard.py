"""Regression cases for accidental credential commits and indexed Markdown links."""

import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_workflow.py"
SPEC = importlib.util.spec_from_file_location("workflow_guard", SCRIPT)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class GuardTests(unittest.TestCase):
    def test_private_paths_rejected_but_placeholder_template_allowed(self):
        for path in (".env", ".env.local", "nested/.env", "config.toml", ".private/x", "secrets/x", "research/evidence.json", "mini-assistant/src/main.rs", "id_ed25519", "x.pem"):
            with self.subTest(path=path):
                self.assertTrue(guard.forbidden_path(path))
        self.assertEqual(guard.inspect_blob(".env.example", b"HA_TOKEN=your_token_here\n"), [])

    def test_realistic_credential_in_template_rejected_without_echo(self):
        fake_token = ("gh" + "p_" + "a" * 36).encode()
        errors = guard.inspect_blob(".env.example", b"TOKEN=" + fake_token)
        self.assertTrue(errors)
        self.assertNotIn(fake_token.decode(), str(errors))

    def test_oversized_artifact_rejected(self):
        self.assertTrue(guard.inspect_blob("notes.txt", b"x" * (guard.MAX_BYTES + 1)))

    def test_relative_links_and_code_fences(self):
        data = b"[ok](../README.md)\n[web](https://example.org)\n```sh\n[x](missing.md)\n```\n"
        self.assertEqual(guard.broken_links("docs/flow.md", data, {"README.md"}), [])
        self.assertTrue(guard.broken_links("README.md", b"[bad](missing.md)", {"README.md"}))
        self.assertTrue(guard.broken_links("README.md", b"[bad](../outside.md)", {"outside.md"}))

    def test_encoded_space_and_directory_links(self):
        self.assertEqual(guard.broken_links("README.md", b"[ok](docs/a%20b.md) [dir](docs/)", {"docs/a b.md"}), [])

    def test_staged_check_reads_index_not_dirty_working_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)

            git("init", "--quiet")
            (root / "README.md").write_text("# Safe staged file\n")
            git("add", "README.md")
            (root / "README.md").write_text("[dirty](missing.md)\n")
            with patch.object(guard, "ROOT", root), patch("sys.argv", [str(SCRIPT), "--staged"]):
                self.assertEqual(guard.main(), 0)

    def test_untracked_link_target_does_not_pass_index_check(self):
        self.assertTrue(guard.broken_links("README.md", b"[new](new.md)", {"README.md"}))

    def test_deleting_target_breaks_unchanged_indexed_document(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)

            git("init", "--quiet")
            (root / "README.md").write_text("[target](target.md)\n")
            (root / "target.md").write_text("# Target\n")
            git("add", "README.md", "target.md")
            git("-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "--quiet", "-m", "fixture")
            git("rm", "--quiet", "target.md")
            with patch.object(guard, "ROOT", root), patch("sys.argv", [str(SCRIPT), "--staged"]), patch("sys.stderr", new_callable=io.StringIO) as errors:
                self.assertEqual(guard.main(), 1)
                self.assertIn("README.md", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
