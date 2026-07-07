#!/usr/bin/env bash
# shellcheck disable=SC1091
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
  source "$script_dir/lib/context.sh"
  prepare_deploy_context

  case "$role" in
    data)
      source "$script_dir/services/cloudflare.sh"
      source "$script_dir/services/polaris.sh"
      source "$script_dir/services/redpanda.sh"
      source "$script_dir/services/seaweedfs.sh"
      source "$script_dir/roles/data.sh"
      deploy_data_role
      ;;
    control)
      source "$script_dir/services/airflow.sh"
      source "$script_dir/services/app.sh"
      source "$script_dir/services/cloudflare.sh"
      source "$script_dir/services/spark.sh"
      source "$script_dir/roles/control.sh"
      deploy_control_role
      ;;
    processing)
      source "$script_dir/services/ingestion.sh"
      source "$script_dir/services/spark.sh"
      source "$script_dir/roles/processing.sh"
      deploy_processing_role
      ;;
    *)
      echo "Unknown deployment role: $role" >&2
      exit 1
      ;;
  esac
  write_deployment_metadata
}

prepare_streamed_deploy() {
  local role="" image_tag="" infra_ref="" config_ref="" cicd_ref=""
  local app_ref="" orchestration_ref="" pipelines_ref="" platform_lib_ref=""

  while (($# > 0)); do
    case "$1" in
      --role)
        role="${2:?--role requires a value}"
        shift 2
        ;;
      --image-tag)
        image_tag="${2:?--image-tag requires a value}"
        shift 2
        ;;
      --infra-ref)
        infra_ref="${2:?--infra-ref requires a value}"
        shift 2
        ;;
      --config-ref)
        config_ref="${2:?--config-ref requires a value}"
        shift 2
        ;;
      --cicd-ref)
        cicd_ref="${2:?--cicd-ref requires a value}"
        shift 2
        ;;
      --app-ref)
        app_ref="${2:?--app-ref requires a value}"
        shift 2
        ;;
      --orchestration-ref)
        orchestration_ref="${2:?--orchestration-ref requires a value}"
        shift 2
        ;;
      --pipelines-ref)
        pipelines_ref="${2:?--pipelines-ref requires a value}"
        shift 2
        ;;
      --platform-lib-ref)
        platform_lib_ref="${2:?--platform-lib-ref requires a value}"
        shift 2
        ;;
      *)
        echo "Unknown deploy argument: $1" >&2
        exit 1
        ;;
    esac
  done

  : "${role:?--role is required}"
  : "${image_tag:?--image-tag is required}"
  : "${infra_ref:?--infra-ref is required}"
  : "${config_ref:?--config-ref is required}"
  : "${cicd_ref:?--cicd-ref is required}"
  : "${platform_lib_ref:?--platform-lib-ref is required}"

  case "$role" in
    data) ;;
    control)
      export VN_NEWS_DEPLOY_ORCHESTRATION_REF="${orchestration_ref:?--orchestration-ref is required}"
      export VN_NEWS_DEPLOY_APP_REF="${app_ref:?--app-ref is required}"
      export VN_NEWS_DEPLOY_PIPELINES_REF="${pipelines_ref:?--pipelines-ref is required}"
      ;;
    processing)
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
  export VN_NEWS_IMAGE_TAG="$image_tag"
  export VN_NEWS_DEPLOY_INFRA_REF="$infra_ref"
  export VN_NEWS_DEPLOY_CONFIG_REF="$config_ref"
  export VN_NEWS_DEPLOY_PLATFORM_LIB_REF="$platform_lib_ref"

  exec bash "$repos_root/vn-news-cicd/scripts/deploy/production.sh"
}

if [[ "${VN_NEWS_DEPLOY_INTERNAL:-0}" == "1" ]]; then
  run_role
else
  prepare_streamed_deploy "$@"
fi
