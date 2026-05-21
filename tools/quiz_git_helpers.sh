#!/usr/bin/env bash

QUIZ_REMOTE_URL="https://github.com/MY221B/feather-flash-quiz.git"
QUIZ_ASKPASS_SCRIPT=""

cleanup_quiz_askpass() {
  if [[ -n "${QUIZ_ASKPASS_SCRIPT}" && -f "${QUIZ_ASKPASS_SCRIPT}" ]]; then
    rm -f "${QUIZ_ASKPASS_SCRIPT}"
  fi
}
trap cleanup_quiz_askpass EXIT

ensure_quiz_submodule() {
  local repo_root="$1"
  local quiz_dir="$2"
  local quiz_top
  local origin_url

  git -C "${repo_root}" submodule update --init feather-flash-quiz

  if ! quiz_top="$(git -C "${quiz_dir}" rev-parse --show-toplevel 2>/dev/null)"; then
    echo "❌ feather-flash-quiz 不是可用的 Git 仓库"
    exit 1
  fi

  if [[ "${quiz_top}" != "${quiz_dir}" ]]; then
    echo "❌ feather-flash-quiz 子模块未正确初始化，拒绝在主仓库中执行子模块 Git 操作"
    exit 1
  fi

  origin_url="$(git -C "${quiz_dir}" config --get remote.origin.url 2>/dev/null || true)"
  if [[ -z "${origin_url}" ]]; then
    git -C "${quiz_dir}" remote add origin "${QUIZ_REMOTE_URL}"
  elif [[ "${origin_url}" == *x-access-token:* ]]; then
    git -C "${quiz_dir}" remote set-url origin "${QUIZ_REMOTE_URL}"
    echo "✅ 已移除 feather-flash-quiz remote 中持久化的 token"
  elif [[ -n "${FEATHER_FLASH_QUIZ_TOKEN:-}" && "${origin_url}" == *"${FEATHER_FLASH_QUIZ_TOKEN}"* ]]; then
    git -C "${quiz_dir}" remote set-url origin "${QUIZ_REMOTE_URL}"
    echo "✅ 已移除 feather-flash-quiz remote 中持久化的 token"
  fi
}

prepare_quiz_askpass() {
  if [[ -z "${FEATHER_FLASH_QUIZ_TOKEN:-}" || -n "${QUIZ_ASKPASS_SCRIPT}" ]]; then
    return 0
  fi

  QUIZ_ASKPASS_SCRIPT="$(mktemp)"
  chmod 700 "${QUIZ_ASKPASS_SCRIPT}"
  cat > "${QUIZ_ASKPASS_SCRIPT}" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  *Username*) printf '%s\n' "x-access-token" ;;
  *Password*) printf '%s\n' "${FEATHER_FLASH_QUIZ_TOKEN:?}" ;;
  *) printf '\n' ;;
esac
EOF
}

quiz_git_with_auth() {
  if [[ -n "${FEATHER_FLASH_QUIZ_TOKEN:-}" ]]; then
    prepare_quiz_askpass
    GIT_ASKPASS="${QUIZ_ASKPASS_SCRIPT}" GIT_TERMINAL_PROMPT=0 git "$@"
  else
    git "$@"
  fi
}
