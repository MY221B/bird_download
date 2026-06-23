import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(command, cwd, env=None, check=True):
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def write_executable(path, content):
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def init_git_repo(path):
    run(["git", "init", "-b", "main"], path)
    run(["git", "config", "user.name", "Test User"], path)
    run(["git", "config", "user.email", "test@example.com"], path)


class WeeklyRefreshScriptTests(unittest.TestCase):
    def make_repo(self, script_name, refresh_script, initialized_quiz=False):
        tmpdir = tempfile.TemporaryDirectory()
        temp_root = Path(tmpdir.name)
        repo = temp_root / "repo"
        repo.mkdir()
        tools = repo / "tools"
        tools.mkdir()

        shutil.copy2(REPO_ROOT / "tools" / script_name, tools / script_name)
        write_executable(
            tools / "sync_from_lovable.sh",
            """
            #!/usr/bin/env bash
            exit 0
            """,
        )
        write_executable(
            tools / "sync_to_lovable.sh",
            """
            #!/usr/bin/env bash
            exit 0
            """,
        )
        (tools / "cloudinary_credentials.py").write_text(
            "def resolve_cloudinary_credentials():\n    return ('demo', 'key', 'secret')\n",
            encoding="utf-8",
        )
        (tools / refresh_script).write_text(
            textwrap.dedent(
                """
                from pathlib import Path

                root = Path(__file__).resolve().parents[1]
                marker = root / "refresh-output.txt"
                marker.write_text("refreshed\\n", encoding="utf-8")
                """
            ).lstrip(),
            encoding="utf-8",
        )

        quiz = repo / "feather-flash-quiz"
        if initialized_quiz:
            (quiz / "scripts").mkdir(parents=True)
            (quiz / "scripts" / "generate-location-birds-manifest.js").write_text(
                "// clean manifest generator fixture\n",
                encoding="utf-8",
            )
            init_git_repo(quiz)
            run(["git", "add", "."], quiz)
            run(["git", "commit", "-m", "initial quiz"], quiz)
            run(
                [
                    "git",
                    "remote",
                    "add",
                    "origin",
                    "https://github.com/MY221B/feather-flash-quiz.git",
                ],
                quiz,
            )
        else:
            quiz.mkdir()

        init_git_repo(repo)
        run(["git", "add", "tools"], repo)
        if initialized_quiz:
            quiz_head = run(["git", "rev-parse", "HEAD"], quiz).stdout.strip()
            run(
                [
                    "git",
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"160000,{quiz_head},feather-flash-quiz",
                ],
                repo,
            )
        run(["git", "commit", "-m", "initial main"], repo)

        remote = temp_root / "origin.git"
        run(["git", "init", "--bare", "--initial-branch=main", str(remote)], temp_root)
        run(["git", "remote", "add", "origin", str(remote)], repo)
        run(["git", "push", "-u", "origin", "main"], repo)

        bin_dir = temp_root / "bin"
        bin_dir.mkdir()
        write_executable(
            bin_dir / "node",
            """
            #!/usr/bin/env bash
            exit 0
            """,
        )
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
        env["EBIRD_TOKEN"] = "test-ebird-token"
        return tmpdir, repo, quiz, env

    def assert_main_refresh_committed_and_pushed(self, repo):
        status = run(["git", "status", "--porcelain"], repo).stdout.strip()
        self.assertEqual(status, "")
        subject = run(["git", "log", "-1", "--format=%s"], repo).stdout.strip()
        self.assertIn("weekly refresh", subject)
        ahead = run(["git", "rev-list", "--count", "origin/main..HEAD"], repo).stdout.strip()
        self.assertEqual(ahead, "0")
        self.assertEqual((repo / "refresh-output.txt").read_text(encoding="utf-8"), "refreshed\n")

    def test_weekly_script_continues_main_push_when_quiz_is_not_checked_out(self):
        for script_name, refresh_script in [
            ("weekly_refresh_and_push.sh", "run_weekly_refresh.py"),
            ("v2_weekly_refresh_and_push.sh", "run_weekly_refresh_v2.py"),
        ]:
            with self.subTest(script=script_name):
                tmpdir, repo, _quiz, env = self.make_repo(script_name, refresh_script)
                self.addCleanup(tmpdir.cleanup)

                result = run(["bash", f"tools/{script_name}"], repo, env=env)

                self.assertRegex(result.stdout, r"(skipping quiz commit|跳过子仓库提交)")
                self.assert_main_refresh_committed_and_pushed(repo)

    def test_v2_token_does_not_persist_to_quiz_remote_or_skip_main_push(self):
        tmpdir, repo, quiz, env = self.make_repo(
            "v2_weekly_refresh_and_push.sh",
            "run_weekly_refresh_v2.py",
            initialized_quiz=True,
        )
        self.addCleanup(tmpdir.cleanup)
        env["FEATHER_FLASH_QUIZ_TOKEN"] = "super-secret-token"

        result = run(["bash", "tools/v2_weekly_refresh_and_push.sh"], repo, env=env)

        self.assertIn("不写入 Git remote 配置", result.stdout)
        quiz_remote = run(["git", "config", "--get", "remote.origin.url"], quiz).stdout.strip()
        self.assertEqual(quiz_remote, "https://github.com/MY221B/feather-flash-quiz.git")
        self.assertNotIn("super-secret-token", quiz_remote)
        self.assert_main_refresh_committed_and_pushed(repo)


if __name__ == "__main__":
    unittest.main()
