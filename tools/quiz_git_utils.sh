#!/usr/bin/env bash

QUIZ_GIT_REMOTE_URL="https://github.com/MY221B/feather-flash-quiz.git"

quiz_git_is_independent_repo() {
  local quiz_dir="$1"
  local top

  [[ -d "${quiz_dir}" ]] || return 1
  [[ -e "${quiz_dir}/.git" ]] || return 1

  top="$(git -C "${quiz_dir}" rev-parse --show-toplevel 2>/dev/null)" || return 1
  [[ "${top}" == "${quiz_dir}" ]]
}

quiz_git_print_skip() {
  local quiz_dir="$1"
  echo "⚠️  ${quiz_dir} 不是独立 Git worktree，跳过 feather-flash-quiz 的 git 同步/提交/推送"
  echo "   这可避免在子目录缺少 .git 时误操作父仓库。"
}

quiz_git_auth_header() {
  printf 'x-access-token:%s' "${FEATHER_FLASH_QUIZ_TOKEN}" | base64 | tr -d '\n'
}

quiz_git_pull_rebase() {
  local branch="$1"

  if [[ -n "${FEATHER_FLASH_QUIZ_TOKEN:-}" ]]; then
    git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $(quiz_git_auth_header)" \
      pull --rebase "${QUIZ_GIT_REMOTE_URL}" "${branch}"
  else
    git pull --rebase origin "${branch}"
  fi
}

quiz_git_push() {
  local refspec="$1"

  if [[ -n "${FEATHER_FLASH_QUIZ_TOKEN:-}" ]]; then
    git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $(quiz_git_auth_header)" \
      push --quiet "${QUIZ_GIT_REMOTE_URL}" "${refspec}"
  else
    git push --quiet origin "${refspec}"
  fi
}
