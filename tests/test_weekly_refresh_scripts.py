import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class WeeklyRefreshScriptTests(unittest.TestCase):
    def test_main_repo_push_runs_when_quiz_has_no_changes(self):
        for script_name in ("weekly_refresh_and_push.sh", "v2_weekly_refresh_and_push.sh"):
            for quiz_has_git in (False, True):
                with self.subTest(script_name=script_name, quiz_has_git=quiz_has_git):
                    self._run_script_and_assert_main_push(script_name, quiz_has_git)

    def _run_script_and_assert_main_push(self, script_name, quiz_has_git):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools_dir = root / "tools"
            quiz_dir = root / "feather-flash-quiz"
            bin_dir = root / "bin"
            tools_dir.mkdir()
            quiz_dir.mkdir()
            bin_dir.mkdir()

            if quiz_has_git:
                (quiz_dir / ".git").write_text(
                    "gitdir: ../.git/modules/feather-flash-quiz\n",
                    encoding="utf-8",
                )

            script_source = REPO_ROOT / "tools" / script_name
            script_copy = tools_dir / script_name
            script_copy.write_text(script_source.read_text(encoding="utf-8"), encoding="utf-8")
            script_copy.chmod(0o755)

            for sync_name in ("sync_from_lovable.sh", "sync_to_lovable.sh"):
                sync_script = tools_dir / sync_name
                sync_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
                sync_script.chmod(0o755)

            self._write_fake_python(bin_dir / "python3")
            self._write_fake_node(bin_dir / "node")
            self._write_fake_git(bin_dir / "git", root, quiz_dir)

            command_log = root / "commands.log"
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}:{env['PATH']}",
                    "COMMAND_LOG": str(command_log),
                    "EBIRD_TOKEN": "test-token",
                    "CLOUDINARY_CLOUD_NAME": "test-cloud",
                    "CLOUDINARY_API_KEY": "test-key",
                    "CLOUDINARY_API_SECRET": "test-secret",
                }
            )

            result = subprocess.run(
                ["bash", str(script_copy)],
                cwd=str(root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertTrue((root / "main_repo_generated.txt").exists())

            log = command_log.read_text(encoding="utf-8")
            self.assertIn(f"{root}|add -A", log)
            self.assertIn(f"{root}|push --quiet origin main", log)
            if not quiz_has_git:
                self.assertNotIn(f"{quiz_dir}|", log)

    @staticmethod
    def _write_fake_python(path):
        path.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                if [[ "$1" == "-c" ]]; then
                  exit 0
                fi
                if [[ "$1" == tools/run_weekly_refresh.py || "$1" == tools/run_weekly_refresh_v2.py ]]; then
                  printf 'generated\\n' > main_repo_generated.txt
                  exit 0
                fi
                exit 0
                """
            ),
            encoding="utf-8",
        )
        path.chmod(0o755)

    @staticmethod
    def _write_fake_node(path):
        path.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                printf '%s|node %s\\n' "$PWD" "$*" >> "$COMMAND_LOG"
                exit 0
                """
            ),
            encoding="utf-8",
        )
        path.chmod(0o755)

    @staticmethod
    def _write_fake_git(path, root, quiz_dir):
        path.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                printf '%s|%s\\n' "$PWD" "$*" >> "$COMMAND_LOG"

                if [[ "$1" == "status" ]]; then
                  if [[ "$2" == "--porcelain" && "$PWD" == "{root}" ]]; then
                    printf 'M main_repo_generated.txt\\n'
                  fi
                  if [[ "$2" == "--porcelain" && "$PWD" == "{quiz_dir}" ]]; then
                    exit 0
                  fi
                  exit 0
                fi
                if [[ "$1" == "diff" && "$2" == "--cached" && "$3" == "--numstat" ]]; then
                  printf '1\\t0\\tmain_repo_generated.txt\\n'
                  exit 0
                fi
                if [[ "$1" == "diff" && "$2" == "--cached" && "$3" == "--quiet" ]]; then
                  exit 1
                fi
                if [[ "$1" == "diff" && "$2" == "HEAD~1" && "$3" == "--shortstat" ]]; then
                  printf ' 1 file changed, 1 insertion(+), 0 deletions(-)\\n'
                  exit 0
                fi
                if [[ "$1" == "rev-parse" ]]; then
                  printf 'main\\n'
                  exit 0
                fi
                exit 0
                """
            ),
            encoding="utf-8",
        )
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
