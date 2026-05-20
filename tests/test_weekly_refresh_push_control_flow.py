#!/usr/bin/env python3
"""Regression tests for weekly refresh push control flow."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def configure_git(repo: Path) -> None:
    run(["git", "config", "user.name", "Weekly Test"], repo)
    run(["git", "config", "user.email", "weekly@example.com"], repo)


def create_quiz_repo(path: Path) -> None:
    path.mkdir()
    run(["git", "init", "--initial-branch=main"], path)
    configure_git(path)
    (path / "scripts").mkdir()
    (path / "README.md").write_text("quiz\n", encoding="utf-8")
    run(["git", "add", "."], path)
    run(["git", "commit", "-m", "init quiz"], path)
    run(["git", "remote", "add", "origin", "https://github.com/MY221B/feather-flash-quiz.git"], path)


def create_fake_main_repo(script_name: str) -> tuple[Path, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix=f"weekly-refresh-{script_name}-"))
    remote = temp_root / "origin.git"
    repo = temp_root / "repo"

    run(["git", "init", "--bare", "--initial-branch=main", str(remote)], temp_root)

    repo.mkdir()
    run(["git", "init", "--initial-branch=main"], repo)
    configure_git(repo)

    tools_dir = repo / "tools"
    tools_dir.mkdir()
    shutil.copy2(SOURCE_ROOT / "tools" / script_name, tools_dir / script_name)
    write_executable(
        tools_dir / "sync_from_lovable.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n",
    )
    write_executable(
        tools_dir / "sync_to_lovable.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\necho synced > \"${SYNC_TO_MARKER}\"\n",
    )
    refresh_script = "run_weekly_refresh_v2.py" if script_name.startswith("v2_") else "run_weekly_refresh.py"
    write_executable(
        tools_dir / refresh_script,
        "#!/usr/bin/env python3\nfrom pathlib import Path\nPath('main-data.txt').write_text('updated\\n', encoding='utf-8')\n",
    )
    (repo / "requirements.txt").write_text("", encoding="utf-8")

    create_quiz_repo(repo / "feather-flash-quiz")

    run(["git", "add", "."], repo)
    run(["git", "commit", "-m", "init main"], repo)
    run(["git", "remote", "add", "origin", str(remote)], repo)
    run(["git", "push", "-u", "origin", "main"], repo)

    return repo, temp_root


def test_main_repo_push_continues_when_quiz_repo_is_clean(script_name: str) -> None:
    repo, temp_root = create_fake_main_repo(script_name)
    marker = temp_root / "sync-to-lovable.marker"
    fake_bin = temp_root / "bin"
    fake_bin.mkdir()
    write_executable(fake_bin / "node", "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["SYNC_TO_MARKER"] = str(marker)
    env["FEATHER_FLASH_QUIZ_TOKEN"] = "test-token"

    run(["bash", f"tools/{script_name}"], repo, env=env)

    log = run(["git", "log", "--oneline", "--max-count=2"], repo).stdout
    status = run(["git", "status", "--porcelain"], repo).stdout
    quiz_remote = run(["git", "config", "--get", "remote.origin.url"], repo / "feather-flash-quiz").stdout

    assert "weekly refresh" in log
    assert marker.read_text(encoding="utf-8") == "synced\n"
    assert status == ""
    assert quiz_remote == "https://github.com/MY221B/feather-flash-quiz.git\n"


def main() -> None:
    for script_name in ("weekly_refresh_and_push.sh", "v2_weekly_refresh_and_push.sh"):
        test_main_repo_push_continues_when_quiz_repo_is_clean(script_name)
        print(f"ok - {script_name}")


if __name__ == "__main__":
    main()
