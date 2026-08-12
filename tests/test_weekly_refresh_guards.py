import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_GIT = shutil.which("git") or "git"


class WeeklyRefreshGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name) / "repo"
        self.remote = Path(self.tmp.name) / "remote.git"
        self.bin_dir = Path(self.tmp.name) / "bin"
        self.work.mkdir()
        self.bin_dir.mkdir()

        self._run([REAL_GIT, "init", "--bare", str(self.remote)], cwd=Path(self.tmp.name))
        self._run([REAL_GIT, "init", "-b", "main"], cwd=self.work)
        self._run([REAL_GIT, "config", "user.name", "Test User"], cwd=self.work)
        self._run([REAL_GIT, "config", "user.email", "test@example.com"], cwd=self.work)

        tools = self.work / "tools"
        tools.mkdir()
        for script in (
            "quiz_git_utils.sh",
            "sync_from_lovable.sh",
            "sync_to_lovable.sh",
            "weekly_refresh_and_push.sh",
            "v2_weekly_refresh_and_push.sh",
        ):
            shutil.copy(PROJECT_ROOT / "tools" / script, tools / script)

        manifest_dir = self.work / "feather-flash-quiz" / "scripts"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "generate-location-birds-manifest.js").write_text("", encoding="utf-8")

        self._write_command_stubs()
        self._run([REAL_GIT, "add", "."], cwd=self.work)
        self._run([REAL_GIT, "commit", "-m", "initial"], cwd=self.work)
        self._run([REAL_GIT, "remote", "add", "origin", str(self.remote)], cwd=self.work)
        self._run([REAL_GIT, "push", "-u", "origin", "main"], cwd=self.work)

    def tearDown(self):
        self.tmp.cleanup()

    def test_weekly_scripts_skip_plain_quiz_dir_and_continue_main_commit(self):
        cases = (
            ("weekly_refresh_and_push.sh", "weekly_legacy.txt"),
            ("v2_weekly_refresh_and_push.sh", "weekly_v2.txt"),
        )

        for script, output_file in cases:
            with self.subTest(script=script):
                work, remote, bin_dir = self._fresh_repo()
                env = self._env(bin_dir)

                result = self._run(["bash", f"tools/{script}"], cwd=work, env=env)

                self.assertIn("不是独立 Git worktree", result.stdout)
                self.assertEqual(
                    output_file,
                    self._run([REAL_GIT, "ls-files", output_file], cwd=work).stdout.strip(),
                )
                self.assertEqual(
                    "",
                    self._run(
                        [REAL_GIT, "ls-remote", "--heads", str(remote), "develop_lovable"],
                        cwd=work,
                    ).stdout.strip(),
                )

    def test_lovable_sync_scripts_skip_plain_quiz_dir(self):
        for script in ("sync_from_lovable.sh", "sync_to_lovable.sh"):
            with self.subTest(script=script):
                result = self._run(["bash", f"tools/{script}"], cwd=self.work, env=self._env(self.bin_dir))

                self.assertIn("不是独立 Git worktree", result.stdout)
                self.assertEqual("main", self._run([REAL_GIT, "branch", "--show-current"], cwd=self.work).stdout.strip())

    def test_quiz_token_is_not_written_to_remote_url(self):
        helper = (PROJECT_ROOT / "tools" / "quiz_git_utils.sh").read_text(encoding="utf-8")
        v2_script = (PROJECT_ROOT / "tools" / "v2_weekly_refresh_and_push.sh").read_text(encoding="utf-8")

        self.assertIn("extraheader=AUTHORIZATION: basic", helper)
        self.assertNotIn("remote set-url", v2_script)
        self.assertNotIn("x-access-token:${FEATHER_FLASH_QUIZ_TOKEN}@", v2_script)

    def _fresh_repo(self):
        work = Path(self.tmp.name) / f"repo_{len(list(Path(self.tmp.name).glob('repo_*')))}"
        remote = Path(self.tmp.name) / f"remote_{work.name}.git"
        bin_dir = Path(self.tmp.name) / f"bin_{work.name}"
        shutil.copytree(self.work, work, ignore=shutil.ignore_patterns(".git"))
        shutil.copytree(self.bin_dir, bin_dir)

        self._run([REAL_GIT, "init", "--bare", str(remote)], cwd=Path(self.tmp.name))
        self._run([REAL_GIT, "init", "-b", "main"], cwd=work)
        self._run([REAL_GIT, "config", "user.name", "Test User"], cwd=work)
        self._run([REAL_GIT, "config", "user.email", "test@example.com"], cwd=work)
        self._run([REAL_GIT, "add", "."], cwd=work)
        self._run([REAL_GIT, "commit", "-m", "initial"], cwd=work)
        self._run([REAL_GIT, "remote", "add", "origin", str(remote)], cwd=work)
        self._run([REAL_GIT, "push", "-u", "origin", "main"], cwd=work)
        return work, remote, bin_dir

    def _write_command_stubs(self):
        python_stub = self.bin_dir / "python3"
        python_stub.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                set -euo pipefail
                if [[ "${{1:-}}" == "-c" ]]; then
                  exit 0
                fi
                case "${{1:-}}" in
                  tools/run_weekly_refresh.py|*/tools/run_weekly_refresh.py)
                    printf 'legacy refresh output\\n' > weekly_legacy.txt
                    exit 0
                    ;;
                  tools/run_weekly_refresh_v2.py|*/tools/run_weekly_refresh_v2.py)
                    printf 'v2 refresh output\\n' > weekly_v2.txt
                    exit 0
                    ;;
                esac
                exec {sys.executable!r} "$@"
                """
            ),
            encoding="utf-8",
        )
        python_stub.chmod(python_stub.stat().st_mode | stat.S_IXUSR)

        node_stub = self.bin_dir / "node"
        node_stub.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                echo "node should not run for a plain quiz directory" >&2
                exit 97
                """
            ),
            encoding="utf-8",
        )
        node_stub.chmod(node_stub.stat().st_mode | stat.S_IXUSR)

    def _env(self, bin_dir):
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env.pop("FEATHER_FLASH_QUIZ_TOKEN", None)
        return env

    def _run(self, cmd, cwd, env=None):
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
