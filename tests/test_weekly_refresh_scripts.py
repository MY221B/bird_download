import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_UNDER_TEST = Path(__file__).resolve().parents[1]


def run(cmd, cwd, env=None):
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"cwd: {cwd}\n"
            f"output:\n{result.stdout}"
        )
    return result.stdout


def write_file(path, content, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


class WeeklyRefreshScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "work"
        self.main_remote = Path(self.tmp.name) / "main.git"
        self.quiz_remote = Path(self.tmp.name) / "quiz.git"

        run(["git", "init", "--bare", "--initial-branch=main", str(self.main_remote)], Path(self.tmp.name))
        run(["git", "init", "--bare", "--initial-branch=main", str(self.quiz_remote)], Path(self.tmp.name))

        self._init_quiz_repo()
        self._init_main_repo()

    def tearDown(self):
        self.tmp.cleanup()

    def _init_quiz_repo(self):
        quiz = self.root / "feather-flash-quiz"
        quiz.mkdir(parents=True)
        run(["git", "init", "-b", "main"], quiz)
        run(["git", "config", "user.name", "Test User"], quiz)
        run(["git", "config", "user.email", "test@example.com"], quiz)
        run(["git", "remote", "add", "origin", str(self.quiz_remote)], quiz)
        write_file(
            quiz / "scripts" / "generate-location-birds-manifest.js",
            """
            const fs = require('fs');
            if (process.env.MUTATE_QUIZ === '1') {
              fs.writeFileSync('manifest.txt', String(Date.now()));
            }
            """,
        )
        write_file(quiz / "README.md", "quiz\n")
        run(["git", "add", "."], quiz)
        run(["git", "commit", "-m", "initial quiz"], quiz)
        run(["git", "push", "-u", "origin", "main"], quiz)

    def _init_main_repo(self):
        self.root.mkdir(exist_ok=True)
        run(["git", "init", "-b", "main"], self.root)
        run(["git", "config", "user.name", "Test User"], self.root)
        run(["git", "config", "user.email", "test@example.com"], self.root)
        run(["git", "remote", "add", "origin", str(self.main_remote)], self.root)

        tools = self.root / "tools"
        tools.mkdir(exist_ok=True)
        for script_name in ("weekly_refresh_and_push.sh", "v2_weekly_refresh_and_push.sh"):
            dest = tools / script_name
            shutil.copy2(REPO_UNDER_TEST / "tools" / script_name, dest)
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR)

        write_file(tools / "sync_from_lovable.sh", "exit 0\n", executable=True)
        write_file(tools / "sync_to_lovable.sh", "exit 0\n", executable=True)
        write_file(
            tools / "run_weekly_refresh.py",
            """
            from pathlib import Path
            Path('generated_by_refresh.txt').write_text('weekly\\n', encoding='utf-8')
            """,
        )
        write_file(
            tools / "run_weekly_refresh_v2.py",
            """
            from pathlib import Path
            Path('generated_by_refresh.txt').write_text('v2\\n', encoding='utf-8')
            """,
        )
        write_file(self.root / "README.md", "main\n")

        run(["git", "add", "."], self.root)
        run(["git", "commit", "-m", "initial main"], self.root)
        run(["git", "push", "-u", "origin", "main"], self.root)

    def test_clean_quiz_still_commits_main_repo_changes(self):
        for script_name in ("weekly_refresh_and_push.sh", "v2_weekly_refresh_and_push.sh"):
            with self.subTest(script_name=script_name):
                self.tearDown()
                self.setUp()

                run(["bash", f"tools/{script_name}"], self.root)

                log = run(["git", "log", "--oneline", "--", "generated_by_refresh.txt"], self.root)
                self.assertIn("weekly refresh", log)
                status = run(["git", "status", "--porcelain"], self.root)
                self.assertEqual("", status)

    def test_v2_token_is_not_persisted_in_quiz_remote(self):
        env = os.environ.copy()
        env["FEATHER_FLASH_QUIZ_TOKEN"] = "sensitive-token"
        env["MUTATE_QUIZ"] = "1"

        run(["bash", "tools/v2_weekly_refresh_and_push.sh"], self.root, env=env)

        remote_url = run(["git", "config", "--get", "remote.origin.url"], self.root / "feather-flash-quiz")
        self.assertNotIn("sensitive-token", remote_url)
        self.assertNotIn("x-access-token", remote_url)


if __name__ == "__main__":
    unittest.main()
