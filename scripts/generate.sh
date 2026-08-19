#!/usr/bin/env bash

set -euo pipefail

proto_dir="/source/proto/v1"
proto_files=(
    "${proto_dir}/common.proto"
    "${proto_dir}/training.proto"
    "${proto_dir}/maze_task.proto"
)
metric_catalog="/source/schemas/maze.metrics.v3.json"
metric_catalog_digest="/source/schemas/maze.metrics.v3.sha256"
cpp_out="/output/cpp"
python_out="/output/python"
schema_out="/output/schemas"

for proto_file in "${proto_files[@]}"; do
    test -f "${proto_file}"
done
test -f "${metric_catalog}"
test -f "${metric_catalog_digest}"
mkdir -p "${cpp_out}" "${python_out}" "${schema_out}"

grpc_plugin="$(command -v grpc_cpp_plugin)"
protoc \
    --proto_path="${proto_dir}" \
    --cpp_out="${cpp_out}" \
    --grpc_out="${cpp_out}" \
    --plugin=protoc-gen-grpc="${grpc_plugin}" \
    "${proto_files[@]}"

python3 -m grpc_tools.protoc \
    --proto_path="${proto_dir}" \
    --python_out="${python_out}" \
    --grpc_python_out="${python_out}" \
    "${proto_files[@]}"

for generated in "${python_out}"/*_pb2.py "${python_out}"/*_pb2_grpc.py; do
    sed -i \
        -e 's/^import common_pb2/from . import common_pb2/' \
        -e 's/^import training_pb2/from . import training_pb2/' \
        -e 's/^import maze_task_pb2/from . import maze_task_pb2/' \
        "${generated}"
done
touch "${python_out}/__init__.py"
cp "${proto_files[@]}" "/output/"
cp "${metric_catalog}" "${metric_catalog_digest}" "${schema_out}/"

python3 - <<'PY'
import json
import platform
import subprocess

import google.protobuf
import grpc


def output(command):
    return subprocess.check_output(command, text=True).strip()


metadata = {
    "generator_schema": "rl-contracts.generator.v1",
    "grpc_python": grpc.__version__,
    "platform_python": platform.python_version(),
    "protobuf_python": google.protobuf.__version__,
    "protoc": output(["protoc", "--version"]),
}
with open("/output/generator-identity.json", "w", encoding="utf-8") as handle:
    json.dump(metadata, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

# Generated artifacts are bind-mounted into development containers. Docker's
# user-namespace mapping must not depend on the host file owner to read them.
find /output -type f -exec chmod 0644 {} +
find /output -type d -exec chmod 0755 {} +
