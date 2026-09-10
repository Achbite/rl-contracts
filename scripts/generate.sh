#!/usr/bin/env bash

set -euo pipefail

profile="${1:-all}"
if [ "$#" -gt 1 ]; then
    echo "usage: generate-contracts [training|task-maze|all]" >&2
    exit 2
fi

source /source/scripts/profiles.sh
select_contract_profile "${profile}"
cd /source
cpp_out="/output/cpp"
python_out="/output/python"
mkdir -p "${cpp_out}" "${python_out}"

grpc_plugin="$(command -v grpc_cpp_plugin)"
protoc --proto_path=/source --cpp_out="${cpp_out}" "${proto_files[@]}"
protoc --proto_path=/source --grpc_out="${cpp_out}" \
    --plugin=protoc-gen-grpc="${grpc_plugin}" "${service_proto_files[@]}"
python3 -m grpc_tools.protoc --proto_path=/source \
    --python_out="${python_out}" "${proto_files[@]}"
python3 -m grpc_tools.protoc --proto_path=/source \
    --grpc_python_out="${python_out}" "${service_proto_files[@]}"

# Task RPC bindings are derived from the same descriptors as the gRPC stubs.
if [ "${#task_service_proto_files[@]}" -gt 0 ]; then
    protoc --proto_path=/source \
        --plugin=protoc-gen-rl_sdk=/source/sdk/tools/protoc-gen-rl-sdk \
        --rl_sdk_out="${cpp_out}" "${task_service_proto_files[@]}"
fi

# Generated imports preserve the category package in every consumer.
find "${python_out}" -type d -exec touch '{}/__init__.py' \;
mkdir -p "${cpp_out}/rl_sdk" /output/sdk
cp -R /source/sdk/include/rl_sdk/. "${cpp_out}/rl_sdk/"
cp -R /source/sdk/. /output/sdk/
cp --parents "${proto_files[@]}" /output/
find /output -type f -exec chmod 0644 {} +
find /output -type d -exec chmod 0755 {} +
chmod 0755 /output/sdk/tools/protoc-gen-rl-sdk
