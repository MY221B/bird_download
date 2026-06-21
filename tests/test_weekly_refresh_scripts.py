import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(cmd, cwd, env=None):
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


class WeeklyRefreshScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.bin_dir = self.base / "bin"
        self.bin_dir.mkdir()
        node = self.bin_dir / "node"
        node.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        node.chmod(node.stat().st_mode | stat.S_IXUSR)

    def tearDown(self):
        self.tmp.cleanup()

    def write_common_stubs(self, repo):
        tools = repo / "tools"
        tools.mkdir()
        (repo / "config").mkdir()
        (repo / "feather-flash-quiz").mkdir()
        (repo / "feather-flash-quiz" / "scripts").mkdir()

        (tools / "sync_from_lovable.sh").write_text(
            "#!/usr/bin/env bash\nexit 0\n",
            encoding="utf-8",
        )
        (tools / "sync_to_lovable.sh").write_text(
            "#!/usr/bin/env bash\nexit 0\n",
            encoding="utf-8",
        )
        (tools / "run_weekly_refresh.py").write_text(
            "from pathlib import Path\nPath('legacy_refresh_output.txt').write_text('legacy refreshed\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )
        (tools / "run_weekly_refresh_v2.py").write_text(
            "from pathlib import Path\nPath('v2_refresh_output.txt').write_text('v2 refreshed\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )
        (tools / "cloudinary_credentials.py").write_text(
            textwrap.dedent(
                """\
                def resolve_cloudinary_credentials():
                    return ("cloud", "key", "secret")
                """
            ),
            encoding="utf-8",
        )
        (repo / "config" / "ebird_token.sh").write_text(
            "export EBIRD_TOKEN=dummy\n",
            encoding="utf-8",
        )
        (repo / "feather-flash-quiz" / "scripts" / "generate-location-birds-manifest.js").write_text(
            "process.exit(0);\n",
            encoding="utf-8",
        )
        for path in tools.glob("*.sh"):
            path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def init_main_repo(self, with_independent_quiz=False):
        repo = self.base / "repo"
        origin = self.base / "origin.git"
        repo.mkdir()
        run(["git", "init", "-b", "main"], repo)
        run(["git", "config", "user.name", "Test User"], repo)
        run(["git", "config", "user.email", "test@example.com"], repo)
        self.write_common_stubs(repo)

        if with_independent_quiz:
            self.init_quiz_repo(repo / "feather-flash-quiz")

        for script_name in ("weekly_refresh_and_push.sh", "v2_weekly_refresh_and_push.sh"):
            shutil.copy2(
                REPO_ROOT / "tools" / script_name,
                repo / "tools" / script_name,
            )

        run(["git", "add", "-A"], repo)
        run(["git", "commit", "-m", "initial"], repo)
        run(["git", "init", "--bare", str(origin)], self.base)
        run(["git", "remote", "add", "origin", str(origin)], repo)
        run(["git", "push", "-u", "origin", "main"], repo)
        return repo, origin

    def init_quiz_repo(self, quiz):
        quiz_origin = self.base / "quiz-origin.git"
        run(["git", "init", "-b", "main"], quiz)
        run(["git", "config", "user.name", "Test User"], quiz)
        run(["git", "config", "user.email", "test@example.com"], quiz)
        run(["git", "add", "-A"], quiz)
        run(["git", "commit", "-m", "initial quiz"], quiz)
        run(["git", "init", "--bare", str(quiz_origin)], self.base)
        run(["git", "remote", "add", "origin", str(quiz_origin)], quiz)
        run(["git", "push", "-u", "origin", "main"], quiz)
        return quiz_origin

    def script_env(self, extra=None):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{env['PATH']}",
                "EBIRD_TOKEN": "dummy",
                "CLOUDINARY_CLOUD_NAME": "cloud",
                "CLOUDINARY_API_KEY": "key",
                "CLOUDINARY_API_SECRET": "secret",
                "GIT_TERMINAL_PROMPT": "0",
            }
        )
        if extra:
            env.update(extra)
        return env

    def run_refresh_script(self, repo, script_name, env=None):
        result = subprocess.run(
            ["bash", f"tools/{script_name}"],
            cwd=repo,
            env=env or self.script_env(),
            text=True,
            capture_output=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def assert_main_refresh_committed_and_pushed(self, repo, origin, output_file):
        self.assertEqual(run(["git", "status", "--porcelain"], repo).stdout, "")
        local_log = run(["git", "log", "-1", "--pretty=%s"], repo).stdout.strip()
        self.assertIn("weekly refresh", local_log)
        pushed_file = run(
            ["git", f"--git-dir={origin}", "show", f"main:{output_file}"],
            repo,
        ).stdout
        self.assertIn("refreshed", pushed_file)

    def test_v2_commits_main_changes_when_quiz_is_not_worktree(self):
        repo, origin = self.init_main_repo(with_independent_quiz=False)

        result = self.run_refresh_script(repo, "v2_weekly_refresh_and_push.sh")

        self.assertIn("feather-flash-quiz", result.stdout)
        self.assert_main_refresh_committed_and_pushed(repo, origin, "v2_refresh_output.txt")

    def test_v2_restores_quiz_remote_when_token_was_injected(self):
        repo, origin = self.init_main_repo(with_independent_quiz=True)
        quiz = repo / "feather-flash-quiz"
        original_remote = run(["git", "remote", "get-url", "origin"], quiz).stdout.strip()

        self.run_refresh_script(
            repo,
            "v2_weekly_refresh_and_push.sh",
            env=self.script_env({"FEATHER_FLASH_QUIZ_TOKEN": "secret-token"}),
        )

        restored_remote = run(["git", "remote", "get-url", "origin"], quiz).stdout.strip()
        self.assertEqual(restored_remote, original_remote)
        self.assertNotIn("secret-token", restored_remote)
        self.assert_main_refresh_committed_and_pushed(repo, origin, "v2_refresh_output.txt")

    def test_legacy_commits_main_changes_when_quiz_is_clean(self):
        repo, origin = self.init_main_repo(with_independent_quiz=True)

        self.run_refresh_script(repo, "weekly_refresh_and_push.sh")

        self.assert_main_refresh_committed_and_pushed(repo, origin, "legacy_refresh_output.txt")


if __name__ == "__main__":
    unittest.main()
