#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
workspace_root="${RL_TRAINING_WORKSPACE:-$(cd "${repo_dir}/.." && pwd -P)}"
version="$(tr -d '[:space:]' < "${repo_dir}/VERSION")"
tool="${repo_dir}/scripts/dev_artifact.py"

if ! command -v docker >/dev/null 2>&1; then
    echo "build_dev_artifact.sh is a host-side Docker entrypoint" >&2
    exit 1
fi
platform="$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')"
platform_dir="${platform//\//-}"
source_digest="$(python3 "${tool}" source-meta --repo "${repo_dir}" --field source_digest)"
output_dir="${workspace_root}/.workspace/dev-artifacts/rl-contracts/${version}/${platform_dir}/${source_digest}"

if [ -d "${output_dir}" ]; then
    python3 "${tool}" verify \
        --root "${output_dir}" \
        --package rl-contracts \
        --version "${version}" \
        --platform "${platform}" \
        --source-digest "${source_digest}"
    printf '%s\n' "${output_dir}"
    exit 0
fi

mkdir -p "$(dirname "${output_dir}")" "${workspace_root}/.workspace/dev-artifacts"
temp_dir="$(mktemp -d "${workspace_root}/.workspace/dev-artifacts/.tmp-contracts.XXXXXX")"
trap 'rm -rf "${temp_dir}"' EXIT
builder_image="rl-training/contracts-dev-builder:${version}-${source_digest:0:12}"

docker build \
    --file "${repo_dir}/Dockerfile.build" \
    --tag "${builder_image}" \
    "${repo_dir}" >&2
docker run --rm \
    --volume "${repo_dir}:/source:ro" \
    --volume "${temp_dir}:/output" \
    "${builder_image}" >&2

python3 "${tool}" finalize-contract \
    --repo "${repo_dir}" \
    --output "${temp_dir}" \
    --version "${version}" \
    --platform "${platform}" \
    --source-digest "${source_digest}"
python3 "${tool}" verify \
    --root "${temp_dir}" \
    --package rl-contracts \
    --version "${version}" \
    --platform "${platform}" \
    --source-digest "${source_digest}"

if [ -e "${output_dir}" ]; then
    echo "development artifact appeared concurrently: ${output_dir}" >&2
    exit 1
fi
mv "${temp_dir}" "${output_dir}"
trap - EXIT
printf '%s\n' "${output_dir}"
