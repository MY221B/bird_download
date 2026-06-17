import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class WeeklyRefreshScriptTests(unittest.TestCase):
    def test_weekly_scripts_commit_main_repo_when_quiz_has_no_changes(self):
        for script_name in ("weekly_refresh_and_push.sh", "v2_weekly_refresh_and_push.sh"):
            with self.subTest(script=script_name):
                result = self.run_script(script_name, checkout_quiz=True)

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assert_quiz_clean_message(result.stdout)
                self.assert_main_repo_was_committed(result.workdir)

    def test_weekly_scripts_commit_main_repo_when_quiz_worktree_is_missing(self):
        for script_name in ("weekly_refresh_and_push.sh", "v2_weekly_refresh_and_push.sh"):
            with self.subTest(script=script_name):
                result = self.run_script(script_name, checkout_quiz=False)

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("跳过子模块提交", result.stdout)
                self.assert_main_repo_was_committed(result.workdir)

    def run_script(self, script_name, checkout_quiz):
        tempdir = tempfile.TemporaryDirectory()
        workdir = Path(tempdir.name)
        try:
            tools_dir = workdir / "tools"
            tools_dir.mkdir()
            script_path = tools_dir / script_name
            shutil.copy2(REPO_ROOT / "tools" / script_name, script_path)

            self.write_executable(tools_dir / "sync_from_lovable.sh", "#!/usr/bin/env bash\nexit 0\n")
            self.write_executable(tools_dir / "sync_to_lovable.sh", "#!/usr/bin/env bash\nexit 0\n")

            if checkout_quiz:
                quiz_dir = workdir / "feather-flash-quiz"
                (quiz_dir / "scripts").mkdir(parents=True)
                (quiz_dir / ".git").write_text("gitdir: ../.git/modules/feather-flash-quiz\n", encoding="utf-8")
                (quiz_dir / "scripts" / "generate-location-birds-manifest.js").write_text("", encoding="utf-8")

            bin_dir = workdir / "bin"
            bin_dir.mkdir()
            self.write_fake_git(bin_dir / "git")
            self.write_fake_python(bin_dir / "python3")
            self.write_executable(bin_dir / "node", "#!/usr/bin/env bash\nexit 0\n")

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
            result = subprocess.run(
                ["bash", str(script_path)],
                cwd=workdir,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            result.workdir = workdir
            result._tempdir = tempdir
            self.addCleanup(tempdir.cleanup)
            return result
        except Exception:
            tempdir.cleanup()
            raise

    def assert_quiz_clean_message(self, stdout):
        self.assertTrue(
            "no changes" in stdout.lower() or "无新改动" in stdout,
            stdout,
        )

    def assert_main_repo_was_committed(self, workdir):
        git_log = (workdir / "git.log").read_text(encoding="utf-8")
        main_commands = [
            line
            for line in git_log.splitlines()
            if f"cwd={workdir}" in line
        ]
        self.assertTrue(
            any("args=commit --quiet -m chore: weekly refresh" in line for line in main_commands),
            git_log,
        )
        self.assertTrue(
            any("args=push --quiet origin main" in line for line in main_commands),
            git_log,
        )

    def write_fake_git(self, path):
        self.write_executable(
            path,
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail
                log="${TEST_WORKSPACE_LOG:-$PWD/git.log}"
                root="$PWD"
                while [[ "$root" != "/" && ! -d "$root/tools" ]]; do
                  root="$(dirname "$root")"
                done
                log="$root/git.log"
                echo "cwd=$PWD args=$*" >> "$log"

                case "$1" in
                  status)
                    if [[ "${2:-}" == "--porcelain" ]]; then
                      case "$PWD" in
                        */feather-flash-quiz) exit 0 ;;
                        *) [[ -f "$root/main_changed" ]] && echo " M examples/gallery_all_cloudinary.html"; exit 0 ;;
                      esac
                    fi
                    echo "On branch main"
                    exit 0
                    ;;
                  diff)
                    if [[ "${2:-}" == "--cached" && "${3:-}" == "--quiet" ]]; then
                      case "$PWD" in
                        */feather-flash-quiz) exit 0 ;;
                        *) [[ -f "$root/main_changed" ]] && exit 1 || exit 0 ;;
                      esac
                    fi
                    if [[ "${2:-}" == "--cached" && "${3:-}" == "--numstat" ]]; then
                      echo "1	0	examples/gallery_all_cloudinary.html"
                      exit 0
                    fi
                    if [[ "${2:-}" == "HEAD~1" && "${3:-}" == "--shortstat" ]]; then
                      echo " 1 file changed, 1 insertion(+)"
                      exit 0
                    fi
                    exit 0
                    ;;
                  add|commit|pull|push)
                    exit 0
                    ;;
                  rev-parse)
                    echo "main"
                    exit 0
                    ;;
                  config)
                    echo "Test User"
                    exit 0
                    ;;
                  remote)
                    exit 0
                    ;;
                  *)
                    exit 0
                    ;;
                esac
                """
            ),
        )

    def write_fake_python(self, path):
        self.write_executable(
            path,
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail
                root="$PWD"
                while [[ "$root" != "/" && ! -d "$root/tools" ]]; do
                  root="$(dirname "$root")"
                done
                echo "cwd=$PWD args=$*" >> "$root/python.log"
                if [[ "${1:-}" == "-c" ]]; then
                  exit 0
                fi
                touch "$root/main_changed"
                exit 0
                """
            ),
        )

    def write_executable(self, path, content):
        path.write_text(content, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
