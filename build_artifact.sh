#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
workspace_root="${RL_TRAINING_WORKSPACE:-$(cd "${repo_dir}/.." && pwd -P)}"
artifact_root="${workspace_root}/.workspace/artifacts/rl-contracts"
version="$(tr -d '[:space:]' < "${repo_dir}/VERSION")"
builder_image="rl-training/contracts-builder:${version}"
profile="${1:-all}"

if [ "$#" -gt 1 ]; then
    echo "usage: bash build_artifact.sh [training|task-maze|all]" >&2
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

docker build \
    --file "${repo_dir}/Dockerfile.build" \
    --tag "${builder_image}" \
    "${repo_dir}"

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
    source "${repo_dir}/scripts/profiles.sh"
    select_contract_profile "${selected}"
    local -a required_files=("sdk/include/rl_sdk/session.h" "sdk/include/rl_sdk/metric_catalog.h")
    local proto_file stem
    for proto_file in "${proto_files[@]}"; do
        stem="${proto_file%.proto}"
        required_files+=("${proto_file}" "cpp/${stem}.pb.cc" "cpp/${stem}.pb.h" "python/${stem}_pb2.py")
    done
    for proto_file in "${service_proto_files[@]}"; do
        stem="${proto_file%.proto}"
        required_files+=("cpp/${stem}.grpc.pb.cc" "cpp/${stem}.grpc.pb.h" "python/${stem}_pb2_grpc.py")
    done

    active_temp="$(mktemp -d "${artifact_root}/.tmp-contracts.XXXXXX")"
    docker run --rm \
        --volume "${repo_dir}:/source:ro" \
        --volume "${active_temp}:/output" \
        "${builder_image}" "${selected}"

    for required in "${required_files[@]}"; do
        test -f "${active_temp}/${required}"
    done

    rm -rf "${output_dir}"
    mv "${active_temp}" "${output_dir}"
    active_temp=""
    printf '%s\n' "${output_dir}"
}

if [ "${profile}" = "all" ]; then
    build_bundle training
    build_bundle task-maze
else
    build_bundle "${profile}"
fi
