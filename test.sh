#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

if [ "$#" -ne 0 ]; then
    echo "usage: bash ./test.sh" >&2
    exit 2
fi

cd "${repo_dir}"
source scripts/profiles.sh
select_contract_profile all

bindings_dir="$(mktemp -d "${TMPDIR:-/tmp}/rl-contracts-test.XXXXXX")"
trap 'rm -rf "${bindings_dir}"' EXIT

python3 -m grpc_tools.protoc \
    --proto_path="${repo_dir}" \
    --python_out="${bindings_dir}" \
    "${proto_files[@]}"
find "${bindings_dir}/proto" -type d -exec touch '{}/__init__.py' \;

PYTHONDONTWRITEBYTECODE=1 \
RL_CONTRACT_TEST_BINDINGS_DIR="${bindings_dir}" \
PYTHONPATH="${repo_dir}${PYTHONPATH:+:${PYTHONPATH}}" \
exec python3 -m unittest -v tests.test_schema \
    tests.test_sdk_distribution.SdkDistributionTest.test_exported_sdk_builds_two_independent_consumers
