#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

role=""
host=""
user=""
image_manifest=""
infra_ref=""
config_ref=""
cicd_ref=""
platform_lib_ref=""
app_ref=""
orchestration_ref=""
pipelines_ref=""

while (($# > 0)); do
  case "$1" in
    --role)
      role="${2:?--role requires a value}"
      shift 2
      ;;
    --host)
      host="${2:?--host requires a value}"
      shift 2
      ;;
    --user)
      user="${2:?--user requires a value}"
      shift 2
      ;;
    --image-manifest)
      image_manifest="${2:?--image-manifest requires a value}"
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
    --platform-lib-ref)
      platform_lib_ref="${2:?--platform-lib-ref requires a value}"
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
    *)
      echo "Unknown remote deploy argument: $1" >&2
      exit 1
      ;;
  esac
done

: "${role:?--role is required}"
: "${host:?--host is required}"
: "${user:?--user is required}"
: "${image_manifest:?--image-manifest is required}"
: "${infra_ref:?--infra-ref is required}"
: "${config_ref:?--config-ref is required}"
: "${cicd_ref:?--cicd-ref is required}"
: "${platform_lib_ref:?--platform-lib-ref is required}"

case "$role" in
  data | processing) ;;
  control)
    : "${app_ref:?--app-ref is required for control}"
    : "${orchestration_ref:?--orchestration-ref is required for control}"
    : "${pipelines_ref:?--pipelines-ref is required for control}"
    ;;
  *)
    echo "Unknown deployment role: $role" >&2
    exit 1
    ;;
esac

ssh_target="$user@$host"
ssh "$ssh_target" bash -s -- "$role" <"$script_dir/preflight_host.sh"

image_manifest_arg="$(printf '%q' "$image_manifest")"
deploy_args=(
  --role "$role"
  --image-manifest "$image_manifest_arg"
  --infra-ref "$infra_ref"
  --config-ref "$config_ref"
  --cicd-ref "$cicd_ref"
  --platform-lib-ref "$platform_lib_ref"
)

if [[ "$role" == "control" ]]; then
  deploy_args+=(
    --orchestration-ref "$orchestration_ref"
    --app-ref "$app_ref"
    --pipelines-ref "$pipelines_ref"
  )
fi

ssh "$ssh_target" bash -s -- "${deploy_args[@]}" <"$script_dir/production.sh"
