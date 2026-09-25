#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
version="$(tr -d '[:space:]' < "${repo_dir}/VERSION")"
builder_image="rl-training/contracts-builder:${version}"
channel="production"
if [ "${1:-}" = "--development" ]; then
    channel="development"
    shift
fi
artifact_root="${RL_ARTIFACT_ROOT:-${repo_dir}/build/artifacts/${channel}}"
profile="${1:-all}"

if [ "$#" -gt 1 ]; then
    echo "usage: bash build_artifact.sh [--development] [training|task-maze|all]" >&2
    exit 2
fi
case "${profile}" in
    training|task-maze|all) ;;
    *)
        echo "unknown Contracts artifact profile: ${profile}" >&2
        exit 2
        ;;
esac

mkdir -p "${artifact_root}"

docker build --provenance=false \
    --file "${repo_dir}/Dockerfile.build" \
    --target toolchain \
    --tag "${builder_image}" \
    "${repo_dir}" >&2

active_temp=""
cleanup() {
    if [ -n "${active_temp}" ] && [ -d "${active_temp}" ]; then
        rm -rf "${active_temp}"
    fi
}
trap cleanup EXIT

build_bundle() {
    local selected="$1"
    local output_dir="${artifact_root}/${selected}"
    if [ "${channel}" = "development" ]; then
        output_dir="${output_dir}/current"
    fi
    source "${repo_dir}/scripts/profiles.sh"
    select_contract_profile "${selected}"
    local -a required_files=("sdk/CMakeLists.txt" "sdk/include/rl_sdk/task_client.h" "sdk/include/rl_sdk/session.h" "sdk/include/rl_sdk/metric_catalog.h"
        "sdk/tools/generate-task" "sdk/tools/protoc-gen-rl-sdk"
        "sdk/proto/common/identity.proto" "sdk/proto/communication/session.proto")
    local proto_file stem
    for proto_file in "${proto_files[@]}"; do
        stem="${proto_file%.proto}"
        required_files+=("${proto_file}" "cpp/${stem}.pb.cc" "cpp/${stem}.pb.h" "python/${stem}_pb2.py")
    done
    for proto_file in "${service_proto_files[@]}"; do
        stem="${proto_file%.proto}"
        required_files+=("cpp/${stem}.grpc.pb.cc" "cpp/${stem}.grpc.pb.h" "python/${stem}_pb2_grpc.py")
    done
    if [ "${#task_service_proto_files[@]}" -gt 0 ]; then
        for proto_file in "${task_service_proto_files[@]}"; do
            stem="${proto_file%.proto}"
            required_files+=("cpp/${stem}.sdk.pb.h")
        done
    fi

    active_temp="$(mktemp -d "${artifact_root}/.tmp-contracts.XXXXXX")"
    docker build --provenance=false --file "${repo_dir}/Dockerfile.build" \
        --target artifact --build-arg "CONTRACT_PROFILE=${selected}" \
        --output "type=local,dest=${active_temp}" "${repo_dir}" >&2

    for required in "${required_files[@]}"; do
        test -f "${active_temp}/${required}"
    done

    mkdir -p "${output_dir}"
    # Compare bytes only to avoid invalidating consumer builds for unchanged input.
    rsync -rcp --delete "${active_temp}/" "${output_dir}/"
    rm -rf "${active_temp}"
    active_temp=""
    printf '%s\n' "${output_dir}"
}

if [ "${profile}" = "all" ]; then
    build_bundle training
    build_bundle task-maze
else
    build_bundle "${profile}"
fi
