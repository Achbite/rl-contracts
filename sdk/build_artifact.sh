#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "usage: bash sdk/build_artifact.sh <output-directory>" >&2
    exit 2
fi
sdk_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
contracts_dir="$(cd "${sdk_dir}/.." && pwd -P)"
mkdir -p "$1"
output_dir="$(cd "$1" && pwd -P)"
stage="$(mktemp -d "${output_dir}/.rl-sdk.XXXXXX")"
trap 'rm -rf "${stage}"' EXIT
mkdir -p "${stage}/RL-SDK/tools" "${stage}/RL-SDK/proto/common" "${stage}/RL-SDK/proto/communication"
cp "${sdk_dir}/CMakeLists.txt" "${sdk_dir}/README.md" "${stage}/RL-SDK/"
cp -R "${sdk_dir}/include" "${stage}/RL-SDK/"
cp "${sdk_dir}/tools/generate-task" "${sdk_dir}/tools/protoc-gen-rl-sdk" "${stage}/RL-SDK/tools/"
cp "${contracts_dir}/proto/common/identity.proto" "${stage}/RL-SDK/proto/common/"
cp "${contracts_dir}/proto/communication/session.proto" "${stage}/RL-SDK/proto/communication/"
cp "${contracts_dir}/LICENSE" "${stage}/RL-SDK/"
chmod 0755 "${stage}/RL-SDK/tools/"*
tar -czf "${stage}/RL-SDK.tar.gz" -C "${stage}" RL-SDK
mv "${stage}/RL-SDK.tar.gz" "${output_dir}/RL-SDK.tar.gz"
printf '%s\n' "${output_dir}/RL-SDK.tar.gz"
