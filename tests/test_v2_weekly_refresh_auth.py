import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "tools" / "v2_weekly_refresh_and_push.sh"


class V2WeeklyRefreshAuthTests(unittest.TestCase):
    def setUp(self):
        self.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_token_auth_does_not_persist_remote_url(self):
        self.assertNotIn("git remote set-url origin \"https://x-access-token:${FEATHER_FLASH_QUIZ_TOKEN}", self.script)
        self.assertIn("GIT_ASKPASS", self.script)
        self.assertIn('git -c remote.origin.url="${QUIZ_REMOTE_URL}"', self.script)
        self.assertIn('-c remote.origin.pushurl="${QUIZ_REMOTE_URL}"', self.script)
        self.assertIn("run_quiz_git push --quiet origin main", self.script)
        self.assertIn("run_quiz_git push --quiet origin main:develop_lovable", self.script)

    def test_submodule_guard_runs_before_child_directory_git_operations(self):
        guard_index = self.script.index('if [[ ! -e "${QUIZ_DIR}/.git" ]]')
        cd_index = self.script.index('cd "${QUIZ_DIR}"')
        self.assertLess(guard_index, cd_index)

    def test_no_quiz_changes_still_allows_main_repo_publish(self):
        main_publish_index = self.script.index("# 🔄 推送主仓库改动")
        no_change_index = self.script.index("feather-flash-quiz 无新改动，跳过提交")
        self.assertLess(no_change_index, main_publish_index)
        self.assertNotIn("exit 0", self.script[no_change_index:main_publish_index])


if __name__ == "__main__":
    unittest.main()
