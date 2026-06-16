import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


FAKE_GIT = """#!/usr/bin/env bash
set -euo pipefail
printf '%s|%s\\n' "$(pwd)" "$*" >> "${GIT_LOG}"

if [[ "${1:-}" == "remote" && "${2:-}" == "set-url" ]]; then
  echo "remote set-url must not be used" >> "${GIT_LOG}"
  exit 42
fi

in_quiz=0
if [[ "$(basename "$(pwd)")" == "feather-flash-quiz" ]]; then
  in_quiz=1
fi

case "$*" in
  "status --porcelain")
    if [[ "${in_quiz}" -eq 1 ]]; then
      if [[ "${QUIZ_STATUS:-clean}" == "dirty" ]]; then
        echo " M location_birds_manifest.json"
      fi
    else
      echo " M main_change.txt"
    fi
    ;;
  "add -A")
    ;;
  "diff --cached --quiet")
    if [[ "${in_quiz}" -eq 1 && "${QUIZ_STATUS:-clean}" != "dirty" ]]; then
      exit 0
    fi
    exit 1
    ;;
  "diff --cached --numstat")
    echo "1	0	main_change.txt"
    ;;
  "diff HEAD~1 --shortstat")
    echo " 1 file changed, 1 insertion(+)"
    ;;
  "config user.name"|"config user.email")
    ;;
  "rev-parse --abbrev-ref HEAD")
    echo "main"
    ;;
  commit*)
    if [[ "${in_quiz}" -eq 1 ]]; then
      echo "quiz" >> "${COMMIT_LOG}"
    else
      echo "main" >> "${COMMIT_LOG}"
    fi
    ;;
  pull*)
    ;;
  push*)
    ;;
  *)
    ;;
esac
"""


FAKE_NODE = """#!/usr/bin/env bash
set -euo pipefail
printf '%s|%s\\n' "$(pwd)" "$*" >> "${NODE_LOG}"
"""


class WeeklyRefreshScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workdir = Path(self.tmp.name)
        self.repo = self.workdir / "repo"
        self.tools = self.repo / "tools"
        self.bin_dir = self.workdir / "bin"
        self.tools.mkdir(parents=True)
        self.bin_dir.mkdir()

        for script_name in (
            "weekly_refresh_and_push.sh",
            "v2_weekly_refresh_and_push.sh",
        ):
            shutil.copy2(
                REPO_ROOT / "tools" / script_name,
                self.tools / script_name,
            )

        self._write_executable(self.tools / "sync_from_lovable.sh", "exit 1\n")
        self._write_executable(
            self.tools / "sync_to_lovable.sh",
            "echo synced > ../sync_to_lovable_ran\n",
        )
        self._write_file(
            self.tools / "run_weekly_refresh.py",
            "from pathlib import Path\nPath('main_change.txt').write_text('weekly')\n",
        )
        self._write_file(
            self.tools / "run_weekly_refresh_v2.py",
            "from pathlib import Path\nPath('main_change.txt').write_text('weekly v2')\n",
        )
        self._write_file(
            self.tools / "cloudinary_credentials.py",
            "def resolve_cloudinary_credentials():\n    return {'cloud_name': 'test'}\n",
        )

        self.git_log = self.workdir / "git.log"
        self.node_log = self.workdir / "node.log"
        self.commit_log = self.workdir / "commits.log"
        self._write_executable(self.bin_dir / "git", FAKE_GIT)
        self._write_executable(self.bin_dir / "node", FAKE_NODE)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scripts_commit_main_repo_when_quiz_worktree_is_missing(self):
        for script_name in (
            "weekly_refresh_and_push.sh",
            "v2_weekly_refresh_and_push.sh",
        ):
            with self.subTest(script=script_name):
                self._reset_logs()
                result = self._run_script(script_name)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("main", self._read_log(self.commit_log))
                self.assertNotIn("quiz", self._read_log(self.commit_log))
                self.assertTrue((self.repo / "sync_to_lovable_ran").exists())

    def test_scripts_commit_main_repo_when_quiz_has_no_changes(self):
        for script_name in (
            "weekly_refresh_and_push.sh",
            "v2_weekly_refresh_and_push.sh",
        ):
            with self.subTest(script=script_name):
                self._reset_logs()
                self._create_quiz_worktree()
                result = self._run_script(script_name, extra_env={"QUIZ_STATUS": "clean"})

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("main", self._read_log(self.commit_log))
                self.assertNotIn("quiz", self._read_log(self.commit_log))
                self.assertIn("generate-location-birds-manifest.js", self._read_log(self.node_log))
                self.assertTrue((self.repo / "sync_to_lovable_ran").exists())

    def test_v2_uses_token_without_persisting_remote_url(self):
        self._create_quiz_worktree()
        result = self._run_script(
            "v2_weekly_refresh_and_push.sh",
            extra_env={
                "QUIZ_STATUS": "dirty",
                "FEATHER_FLASH_QUIZ_TOKEN": "secret-token",
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("quiz", self._read_log(self.commit_log))
        self.assertIn("main", self._read_log(self.commit_log))
        self.assertNotIn("remote set-url", self._read_log(self.git_log))

    def _run_script(self, script_name, extra_env=None):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{env['PATH']}",
                "GIT_LOG": str(self.git_log),
                "NODE_LOG": str(self.node_log),
                "COMMIT_LOG": str(self.commit_log),
                "EBIRD_TOKEN": "test-ebird-token",
            }
        )
        if extra_env:
            env.update(extra_env)

        return subprocess.run(
            ["bash", str(self.tools / script_name)],
            cwd=self.repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def _create_quiz_worktree(self):
        quiz_dir = self.repo / "feather-flash-quiz"
        (quiz_dir / "scripts").mkdir(parents=True)
        self._write_file(quiz_dir / ".git", "gitdir: ../.git/modules/feather-flash-quiz\n")
        self._write_file(
            quiz_dir / "scripts" / "generate-location-birds-manifest.js",
            "",
        )

    def _reset_logs(self):
        for path in (self.git_log, self.node_log, self.commit_log):
            if path.exists():
                path.unlink()
        sync_marker = self.repo / "sync_to_lovable_ran"
        if sync_marker.exists():
            sync_marker.unlink()

    def _read_log(self, path):
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _write_file(self, path, content):
        path.write_text(textwrap.dedent(content), encoding="utf-8")

    def _write_executable(self, path, content):
        self._write_file(path, content)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
