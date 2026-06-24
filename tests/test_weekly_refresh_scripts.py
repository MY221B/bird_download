import os
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_BASH = shutil.which("bash") or "/usr/bin/bash"
REAL_GIT = shutil.which("git") or "/usr/bin/git"


class WeeklyRefreshScriptTests(unittest.TestCase):
    def make_workspace(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        tools_dir = repo / "tools"
        quiz_dir = repo / "feather-flash-quiz"
        bin_dir = repo / "bin"

        tools_dir.mkdir()
        bin_dir.mkdir()
        (quiz_dir / "scripts").mkdir(parents=True)

        for script_name in (
            "weekly_refresh_and_push.sh",
            "v2_weekly_refresh_and_push.sh",
        ):
            shutil.copy2(
                REPO_ROOT / "tools" / script_name,
                tools_dir / script_name,
            )

        self.write_executable(
            tools_dir / "sync_from_lovable.sh",
            "#!/usr/bin/env bash\nexit 0\n",
        )
        self.write_executable(
            tools_dir / "sync_to_lovable.sh",
            "#!/usr/bin/env bash\nexit 0\n",
        )
        self.write_executable(bin_dir / "node", "#!/usr/bin/env bash\nexit 0\n")
        self.write_executable(
            bin_dir / "python3",
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    'if [[ "$1" == "-c" ]]; then',
                    "  exit 0",
                    "fi",
                    'if [[ "$1" == "tools/run_weekly_refresh.py" || "$1" == "tools/run_weekly_refresh_v2.py" ]]; then',
                    '  printf "refreshed by %s\\n" "$1" >> main_data.txt',
                    "  exit 0",
                    "fi",
                    f'exec "{sys.executable}" "$@"',
                    "",
                ]
            ),
        )
        self.write_executable(
            bin_dir / "git",
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    'if [[ "$1" == "pull" || "$1" == "push" ]]; then',
                    "  exit 0",
                    "fi",
                    f'exec "{REAL_GIT}" "$@"',
                    "",
                ]
            ),
        )

        self.run_git(["init"], repo)
        self.run_git(["config", "user.name", "Test User"], repo)
        self.run_git(["config", "user.email", "test@example.com"], repo)
        (repo / ".gitignore").write_text("feather-flash-quiz/\n", encoding="utf-8")
        (repo / "README.md").write_text("fixture\n", encoding="utf-8")
        self.run_git(["add", "."], repo)
        self.run_git(["commit", "-m", "initial"], repo)

        self.run_git(["init"], quiz_dir)
        self.run_git(["config", "user.name", "Test User"], quiz_dir)
        self.run_git(["config", "user.email", "test@example.com"], quiz_dir)
        (quiz_dir / "README.md").write_text("quiz fixture\n", encoding="utf-8")
        self.run_git(["add", "."], quiz_dir)
        self.run_git(["commit", "-m", "initial quiz"], quiz_dir)
        self.run_git(
            [
                "remote",
                "add",
                "origin",
                "https://github.com/MY221B/feather-flash-quiz.git",
            ],
            quiz_dir,
        )

        return types.SimpleNamespace(repo=repo, quiz_dir=quiz_dir, bin_dir=bin_dir)

    def write_executable(self, path: Path, content: str):
        path.write_text(content, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def run_git(self, args, cwd: Path):
        return subprocess.run(
            [REAL_GIT, *args],
            cwd=cwd,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def run_script(self, workspace, script_name: str, extra_env=None):
        env = os.environ.copy()
        env.update(extra_env or {})
        env["PATH"] = f"{workspace.bin_dir}{os.pathsep}{env['PATH']}"
        env["EBIRD_TOKEN"] = env.get("EBIRD_TOKEN", "test-ebird-token")
        return subprocess.run(
            [REAL_BASH, f"tools/{script_name}"],
            cwd=workspace.repo,
            env=env,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )

    def assert_main_refresh_was_committed(self, repo: Path):
        tracked = self.run_git(
            ["ls-files", "--error-unmatch", "main_data.txt"],
            repo,
        )
        self.assertEqual(tracked.stdout.strip(), "main_data.txt")
        status = self.run_git(["status", "--porcelain"], repo)
        self.assertEqual(status.stdout.strip(), "")

    def test_main_repo_changes_are_committed_when_quiz_is_clean(self):
        for script_name in (
            "weekly_refresh_and_push.sh",
            "v2_weekly_refresh_and_push.sh",
        ):
            with self.subTest(script=script_name):
                workspace = self.make_workspace()
                self.run_script(workspace, script_name)

                self.assert_main_refresh_was_committed(workspace.repo)

    def test_v2_token_does_not_persist_in_quiz_remote(self):
        workspace = self.make_workspace()
        self.run_script(
            workspace,
            "v2_weekly_refresh_and_push.sh",
            {"FEATHER_FLASH_QUIZ_TOKEN": "super-secret-token"},
        )

        remote = self.run_git(
            ["remote", "get-url", "origin"],
            workspace.quiz_dir,
        ).stdout.strip()
        self.assertEqual(remote, "https://github.com/MY221B/feather-flash-quiz.git")
        self.assertNotIn("super-secret-token", remote)
        self.assert_main_refresh_was_committed(workspace.repo)


if __name__ == "__main__":
    unittest.main()
