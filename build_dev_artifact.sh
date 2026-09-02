#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
workspace_root="${RL_TRAINING_WORKSPACE:-$(cd "${repo_dir}/.." && pwd -P)}"
version="$(tr -d '[:space:]' < "${repo_dir}/VERSION")"
artifact_root="${workspace_root}/.workspace/dev-artifacts/rl-contracts"
builder_image="rl-training/contracts-dev-builder:${version}"
profile="${1:-all}"

if [ "$#" -gt 1 ]; then
    echo "usage: bash build_dev_artifact.sh [training|task-maze|all]" >&2
    exit 2
fi
case "${profile}" in
    training|task-maze|all) ;;
    *)
        echo "unknown Contracts development artifact profile: ${profile}" >&2
        exit 2
        ;;
esac

if ! command -v docker >/dev/null 2>&1; then
    echo "build_dev_artifact.sh is a host-side Docker entrypoint" >&2
    exit 1
fi

mkdir -p "${artifact_root}/${version}"

docker build \
    --file "${repo_dir}/Dockerfile.build" \
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
    local output_dir="${artifact_root}/${version}/${selected}/current"
    local -a required_files
    case "${selected}" in
        training)
            required_files=(
                cpp/common.pb.cc cpp/training.pb.cc
                cpp/training.grpc.pb.cc cpp/training_metrics.pb.cc
                python/common_pb2.py python/training_pb2.py
                python/training_pb2_grpc.py python/training_metrics_pb2.py
            )
            ;;
        task-maze)
            required_files=(
                cpp/common.pb.cc cpp/maze_task.pb.cc
                cpp/maze_task.grpc.pb.cc cpp/maze_metrics.pb.cc
                python/common_pb2.py python/maze_task_pb2.py
                python/maze_task_pb2_grpc.py python/maze_metrics_pb2.py
            )
            ;;
        *)
            return 2
            ;;
    esac

    active_temp="$(mktemp -d "${artifact_root}/.tmp-contracts.XXXXXX")"
    docker run --rm \
        --volume "${repo_dir}:/source:ro" \
        --volume "${active_temp}:/output" \
        "${builder_image}" "${selected}" >&2

    for required in "${required_files[@]}"; do
        test -f "${active_temp}/${required}"
    done

    mkdir -p "$(dirname "${output_dir}")"
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
