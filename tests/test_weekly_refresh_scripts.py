#!/usr/bin/env python3
"""Regression checks for weekly refresh wrapper control flow."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    ROOT / "tools" / "weekly_refresh_and_push.sh",
    ROOT / "tools" / "v2_weekly_refresh_and_push.sh",
]
MAIN_REPO_MARKER = "# 🔄 推送主仓库改动"


def assert_no_success_exit_before_main_repo_commit(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    if MAIN_REPO_MARKER not in text:
        raise AssertionError(f"{script} is missing the main repository commit marker")

    before_main_repo_commit = text.split(MAIN_REPO_MARKER, 1)[0]
    bad_lines = [
        line_no
        for line_no, line in enumerate(before_main_repo_commit.splitlines(), start=1)
        if line.strip() == "exit 0"
    ]
    if bad_lines:
        raise AssertionError(
            f"{script} exits successfully before committing the main repository: "
            f"lines {bad_lines}"
        )


def assert_quiz_token_is_not_persisted(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    if "git remote set-url origin \"https://x-access-token:${FEATHER_FLASH_QUIZ_TOKEN}" in text:
        raise AssertionError(f"{script} persists FEATHER_FLASH_QUIZ_TOKEN in remote.origin.url")


def main() -> None:
    for script in SCRIPTS:
        assert_no_success_exit_before_main_repo_commit(script)
        assert_quiz_token_is_not_persisted(script)
    print("weekly refresh wrapper checks passed")


if __name__ == "__main__":
    main()
