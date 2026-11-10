"""Offline init-order and fail-safe guards; no actual SSH daemon or keys are used."""

from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "device" / "S99zzmini_ssh"


class MiniSshBootTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mini-ssh-boot-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "persistent data with spaces" / "opt" / "mini-ssh"
        self.runtime = self.root / "run"
        self.runtime.mkdir()
        self.marker = self.root / "daemon-was-invoked"
        content = SCRIPT.read_text()
        replacements = {
            "DIR=/bkupgrade/data/opt/mini-ssh": "DIR=" + shlex.quote(str(self.data)),
            "PIDFILE=/run/mini-ssh.pid": "PIDFILE=" + shlex.quote(str(self.runtime / "mini-ssh.pid")),
            "LOGFILE=/run/mini-ssh.log": "LOGFILE=" + shlex.quote(str(self.runtime / "mini-ssh.log")),
        }
        for old, new in replacements.items():
            self.assertEqual(content.count(old + "\n"), 1)
            content = content.replace(old + "\n", new + "\n")
        self.fixture_script = self.root / "mini-ssh-under-test"
        self.fixture_script.write_text(content)
        self.fixture_script.chmod(0o755)

    def invoke(self):
        return subprocess.run(
            ["/bin/sh", str(self.fixture_script), "start"],
            capture_output=True, text=True, timeout=3,
        )

    def prepare_fake_files(self):
        (self.data / "bin").mkdir(parents=True)
        (self.data / "etc").mkdir()
        daemon = self.data / "bin" / "dropbear"
        daemon.write_text("#!/bin/sh\n: > " + shlex.quote(str(self.marker)) + "\n")
        daemon.chmod(0o755)
        # Plain non-key fixture bytes; the real binary is never invoked.
        (self.data / "etc" / "host_ed25519").write_text("fixture-not-a-key\n")
        (self.data / "etc" / "authorized_keys").write_text("fixture-not-an-authorized-key\n")

    def test_script_syntax_and_canonical_path(self):
        result = subprocess.run(["/bin/sh", "-n", str(SCRIPT)], capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0)
        self.assertIn("DIR=/bkupgrade/data/opt/mini-ssh\n", SCRIPT.read_text())

    def test_disabled_marker_skips_daemon_and_runtime_writes(self):
        self.prepare_fake_files()
        (self.data / "disabled").touch()
        result = self.invoke()
        self.assertEqual(result.returncode, 0)
        self.assertIn("disabled; skipped", result.stdout)
        self.assertFalse(self.marker.exists())
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_missing_required_files_skip_daemon(self):
        self.prepare_fake_files()
        for relative in ["bin/dropbear", "etc/host_ed25519", "etc/authorized_keys"]:
            with self.subTest(missing=relative):
                path = self.data / relative
                held = path.with_name(path.name + ".held")
                path.rename(held)
                try:
                    result = self.invoke()
                    self.assertEqual(result.returncode, 0)
                    self.assertIn("required files unavailable; skipped", result.stdout)
                    self.assertFalse(self.marker.exists())
                    self.assertEqual(list(self.runtime.iterdir()), [])
                finally:
                    held.rename(path)

    def test_rcs_glob_places_ssh_after_onboot_with_start_argument(self):
        init = self.root / "init.d"
        init.mkdir()
        events = self.root / "events"
        ready = self.root / "onboot-ready"
        # Stub onboot, not the vendor script: no mounts, accounts or system paths.
        onboot = init / "S99onboot.sh"
        onboot.write_text(
            "#!/bin/sh\n"
            + "printf 'onboot:%s\\n' \"$1\" >> " + shlex.quote(str(events)) + "\n"
            + ": > " + shlex.quote(str(ready)) + "\n"
        )
        wrapper = init / SCRIPT.name
        wrapper.write_text(
            "#!/bin/sh\n"
            + "printf 'ssh:%s\\n' \"$1\" >> " + shlex.quote(str(events)) + "\n"
            + "[ -f " + shlex.quote(str(ready)) + " ] || exit 41\n"
            + "exec /bin/sh " + shlex.quote(str(self.fixture_script)) + ' "$@"\n'
        )
        wrapper.chmod(0o755)
        # The non-space init directory allows the original rcS loop semantics,
        # including its unquoted $i invocation. The tested DIR still has spaces.
        loop = (
            "for i in " + shlex.quote(str(init)) + "/S??*; do\n"
            '[ ! -f "$i" ] && continue\n'
            'case "$i" in\n'
            '*.sh) (trap - INT QUIT TSTP; set start; . $i) ;;\n'
            '*) $i start ;;\n'
            'esac\ndone\n'
        )
        result = subprocess.run(["/bin/sh", "-c", loop], capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(events.read_text().splitlines(), ["onboot:start", "ssh:start"])
        self.assertIn("required files unavailable; skipped", result.stdout)
        self.assertFalse(self.marker.exists())
        names = ["S98mini_ssh", "S99mini_ssh", "S99onboot.sh", SCRIPT.name]
        self.assertEqual(sorted(names), names)


if __name__ == "__main__":
    unittest.main()
