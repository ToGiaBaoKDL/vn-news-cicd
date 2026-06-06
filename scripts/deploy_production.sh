#!/usr/bin/env bash
set -euo pipefail

deploy_root="${VN_NEWS_DEPLOY_ROOT:-$HOME/vn-news-intelligence}"
repos_root="$deploy_root/repos"
repo_owner="${VN_NEWS_GITHUB_OWNER:-ToGiaBaoKDL}"

checkout_cicd_repo() {
  local commit_ref="$1"
  local repo_dir="$repos_root/vn-news-cicd"

  if [[ ! -d "$repo_dir/.git" ]]; then
    git clone "https://github.com/$repo_owner/vn-news-cicd.git" "$repo_dir"
  fi
  git -C "$repo_dir" fetch --quiet origin "$commit_ref"
  git -C "$repo_dir" checkout --quiet --detach "$commit_ref"
}

run_role() {
  local script_dir

  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  source "$script_dir/deploy/lib/context.sh"
  source "$script_dir/deploy/lib/services.sh"
  source "$script_dir/deploy/lib/bootstrap_actions.sh"
  source "$script_dir/deploy/roles/data.sh"
  source "$script_dir/deploy/roles/control.sh"
  source "$script_dir/deploy/roles/processing.sh"

  prepare_deploy_context

  case "$role" in
    data) deploy_data_role ;;
    control) deploy_control_role ;;
    processing) deploy_processing_role ;;
    *)
      echo "Unknown deployment role: $role" >&2
      exit 1
      ;;
  esac
}

prepare_streamed_deploy() {
  local role="${1:?role is required}"
  local release_tag="${2:?release tag is required}"
  local infra_ref="${3:?infra ref is required}"
  local config_ref cicd_ref

  case "$role" in
    data)
      config_ref=""
      cicd_ref="${4:-${VN_NEWS_CICD_REF:-main}}"
      ;;
    control)
      config_ref="${4:?config ref is required}"
      cicd_ref="${5:?cicd ref is required}"
      export VN_NEWS_DEPLOY_ORCHESTRATION_REF="${6:?orchestration ref is required}"
      export VN_NEWS_DEPLOY_APP_REF="${7:?app ref is required}"
      export VN_NEWS_DEPLOY_PLATFORM_LIB_REF="${8:?platform lib ref is required}"
      ;;
    processing)
      config_ref="${4:?config ref is required}"
      cicd_ref="${5:-${VN_NEWS_CICD_REF:-main}}"
      ;;
    *)
      echo "Unknown deployment role: $role" >&2
      exit 1
      ;;
  esac

  mkdir -p "$repos_root"
  checkout_cicd_repo "$cicd_ref"

  export VN_NEWS_DEPLOY_INTERNAL=1
  export VN_NEWS_DEPLOY_ROLE="$role"
  export VN_NEWS_DEPLOY_RELEASE_TAG="$release_tag"
  export VN_NEWS_DEPLOY_INFRA_REF="$infra_ref"
  export VN_NEWS_DEPLOY_CONFIG_REF="$config_ref"

  exec bash "$repos_root/vn-news-cicd/scripts/deploy_production.sh"
}

if [[ "${VN_NEWS_DEPLOY_INTERNAL:-0}" == "1" ]]; then
  run_role
else
  prepare_streamed_deploy "$@"
fi
