#!/usr/bin/env bash

require_independent_git_checkout() {
  local checkout_dir="$1"
  local repo_label="${2:-repository}"
  local expected_top
  local actual_top

  if [[ ! -d "${checkout_dir}" ]]; then
    echo "ERROR: ${repo_label} directory does not exist: ${checkout_dir}" >&2
    return 1
  fi

  expected_top="$(cd "${checkout_dir}" && pwd -P)"

  if [[ ! -e "${checkout_dir}/.git" ]]; then
    echo "ERROR: ${repo_label} is not an initialized Git checkout: ${checkout_dir}" >&2
    echo "Run: git submodule update --init --recursive ${checkout_dir}" >&2
    return 1
  fi

  if ! actual_top="$(git -C "${checkout_dir}" rev-parse --show-toplevel 2>/dev/null)"; then
    echo "ERROR: ${repo_label} is not a valid Git checkout: ${checkout_dir}" >&2
    return 1
  fi

  actual_top="$(cd "${actual_top}" && pwd -P)"
  if [[ "${actual_top}" != "${expected_top}" ]]; then
    echo "ERROR: ${repo_label} Git commands resolve to ${actual_top}, expected ${expected_top}" >&2
    echo "Refusing to run because this would operate on the parent repository." >&2
    return 1
  fi
}
