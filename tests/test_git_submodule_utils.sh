#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/tools/git_submodule_utils.sh"

assert_fails_parent_checkout() {
  local parent_dir
  local child_dir
  local output
  local status

  parent_dir="$(mktemp -d)"
  child_dir="${parent_dir}/feather-flash-quiz"
  mkdir -p "${child_dir}"

  git -C "${parent_dir}" init --quiet
  git -C "${parent_dir}" config user.name "Test User"
  git -C "${parent_dir}" config user.email "test@example.com"
  touch "${parent_dir}/README.md"
  git -C "${parent_dir}" add README.md
  git -C "${parent_dir}" commit --quiet -m "init"

  set +e
  output="$(require_independent_git_checkout "${child_dir}" "feather-flash-quiz" 2>&1)"
  status=$?
  set -e

  if [[ "${status}" -eq 0 ]]; then
    echo "Expected missing child .git checkout to fail" >&2
    exit 1
  fi

  if [[ "${output}" != *"not an initialized Git checkout"* ]]; then
    echo "Unexpected failure message:" >&2
    echo "${output}" >&2
    exit 1
  fi
}

assert_accepts_independent_checkout() {
  local repo_dir

  repo_dir="$(mktemp -d)"
  git -C "${repo_dir}" init --quiet
  git -C "${repo_dir}" config user.name "Test User"
  git -C "${repo_dir}" config user.email "test@example.com"
  touch "${repo_dir}/README.md"
  git -C "${repo_dir}" add README.md
  git -C "${repo_dir}" commit --quiet -m "init"

  require_independent_git_checkout "${repo_dir}" "standalone-repo"
}

assert_fails_parent_checkout
assert_accepts_independent_checkout

echo "git_submodule_utils tests passed"
