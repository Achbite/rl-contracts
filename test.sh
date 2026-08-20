#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

if [ "$#" -ne 0 ]; then
    echo "usage: bash ./test.sh" >&2
    exit 2
fi

cd "${repo_dir}"

bindings_dir="$(mktemp -d "${TMPDIR:-/tmp}/rl-contracts-test.XXXXXX")"
trap 'rm -rf "${bindings_dir}"' EXIT

python3 -m grpc_tools.protoc \
    --proto_path="${repo_dir}/proto/v1" \
    --python_out="${bindings_dir}" \
    "${repo_dir}/proto/v1/common.proto" \
    "${repo_dir}/proto/v1/training.proto" \
    "${repo_dir}/proto/v1/maze_task.proto"

# TCR-A3-DEVELOPMENT-VALIDATION-008: one generated-message development check.
PYTHONDONTWRITEBYTECODE=1 \
RL_CONTRACT_TEST_BINDINGS_DIR="${bindings_dir}" \
PYTHONPATH="${repo_dir}${PYTHONPATH:+:${PYTHONPATH}}" \
exec python3 -m unittest -v \
    tests.test_schema.A3DevelopmentWireTest.test_fixed_component_messages_round_trip
