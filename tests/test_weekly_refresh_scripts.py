import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_command(args, cwd, env=None):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        args,
        cwd=cwd,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )


class WeeklyRefreshScriptTests(unittest.TestCase):
    def test_weekly_script_commits_main_changes_when_quiz_is_clean(self):
        output, committed = self.run_refresh_script(
            "weekly_refresh_and_push.sh",
            "run_weekly_refresh.py",
            with_quiz_worktree=True,
        )

        self.assertIn("feather-flash-quiz has no changes", output)
        self.assertEqual("weekly_refresh_and_push.sh\n", committed)

    def test_v2_script_commits_main_changes_when_quiz_is_clean(self):
        output, committed = self.run_refresh_script(
            "v2_weekly_refresh_and_push.sh",
            "run_weekly_refresh_v2.py",
            with_quiz_worktree=True,
        )

        self.assertIn("feather-flash-quiz 无新改动", output)
        self.assertEqual("v2_weekly_refresh_and_push.sh\n", committed)

    def test_weekly_script_commits_main_changes_without_quiz_worktree(self):
        output, committed = self.run_refresh_script(
            "weekly_refresh_and_push.sh",
            "run_weekly_refresh.py",
            with_quiz_worktree=False,
        )

        self.assertIn("未检出为独立 Git worktree", output)
        self.assertEqual("weekly_refresh_and_push.sh\n", committed)

    def test_v2_script_commits_main_changes_without_quiz_worktree(self):
        output, committed = self.run_refresh_script(
            "v2_weekly_refresh_and_push.sh",
            "run_weekly_refresh_v2.py",
            with_quiz_worktree=False,
        )

        self.assertIn("未检出为独立 Git worktree", output)
        self.assertEqual("v2_weekly_refresh_and_push.sh\n", committed)

    def run_refresh_script(self, script_name, refresh_script_name, with_quiz_worktree):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            main_remote = tmp_path / "main-remote.git"
            repo = tmp_path / "repo"
            tools_dir = repo / "tools"
            config_dir = repo / "config"
            bin_dir = tmp_path / "bin"

            run_command(["git", "init", "--bare", "--initial-branch=main", str(main_remote)], tmp_path)
            run_command(["git", "init", "--initial-branch=main", str(repo)], tmp_path)
            self.configure_git(repo)

            tools_dir.mkdir()
            config_dir.mkdir()
            bin_dir.mkdir()

            shutil.copy2(REPO_ROOT / "tools" / script_name, tools_dir / script_name)
            self.write_refresh_stub(tools_dir / refresh_script_name, script_name)
            self.write_sync_stub(tools_dir / "sync_from_lovable.sh")
            self.write_sync_stub(tools_dir / "sync_to_lovable.sh")
            self.write_cloudinary_credentials_stub(tools_dir / "cloudinary_credentials.py")
            self.write_fake_node(bin_dir / "node")

            if with_quiz_worktree:
                self.create_clean_quiz_worktree(repo / "feather-flash-quiz", tmp_path / "quiz-remote.git")

            run_command(["git", "remote", "add", "origin", str(main_remote)], repo)
            run_command(["git", "add", "-A"], repo)
            run_command(["git", "commit", "-m", "initial"], repo)
            run_command(["git", "push", "-u", "origin", "main"], repo)

            result = run_command(
                ["bash", f"tools/{script_name}"],
                repo,
                env={
                    "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                    "EBIRD_TOKEN": "test-token",
                },
            )
            committed = run_command(
                ["git", "show", "HEAD:config/generated_from_refresh.txt"],
                repo,
            ).stdout

            return result.stdout, committed

    def configure_git(self, repo):
        run_command(["git", "config", "user.name", "Test User"], repo)
        run_command(["git", "config", "user.email", "test@example.com"], repo)

    def create_clean_quiz_worktree(self, quiz_dir, quiz_remote):
        run_command(["git", "init", "--bare", "--initial-branch=main", str(quiz_remote)], quiz_dir.parent)
        run_command(["git", "init", "--initial-branch=main", str(quiz_dir)], quiz_dir.parent)
        self.configure_git(quiz_dir)
        (quiz_dir / "scripts").mkdir()
        (quiz_dir / "README.md").write_text("quiz\n", encoding="utf-8")
        run_command(["git", "remote", "add", "origin", str(quiz_remote)], quiz_dir)
        run_command(["git", "add", "-A"], quiz_dir)
        run_command(["git", "commit", "-m", "initial quiz"], quiz_dir)
        run_command(["git", "push", "-u", "origin", "main"], quiz_dir)

    def write_refresh_stub(self, path, script_name):
        path.write_text(
            textwrap.dedent(
                f"""\
                import pathlib

                pathlib.Path("config/generated_from_refresh.txt").write_text(
                    {script_name!r} + "\\n",
                    encoding="utf-8",
                )
                """
            ),
            encoding="utf-8",
        )

    def write_sync_stub(self, path):
        path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    def write_cloudinary_credentials_stub(self, path):
        path.write_text(
            textwrap.dedent(
                """\
                def resolve_cloudinary_credentials():
                    return "cloud", "key", "secret"
                """
            ),
            encoding="utf-8",
        )

    def write_fake_node(self, path):
        path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        current_mode = path.stat().st_mode
        path.chmod(current_mode | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
