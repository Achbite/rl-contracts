#!/usr/bin/env bash

set -euo pipefail

proto_file="/source/proto/v1/maze.proto"
cpp_out="/output/cpp"
python_out="/output/python"

test -f "${proto_file}"
mkdir -p "${cpp_out}" "${python_out}"

grpc_plugin="$(command -v grpc_cpp_plugin)"
protoc \
    --proto_path="$(dirname "${proto_file}")" \
    --cpp_out="${cpp_out}" \
    --grpc_out="${cpp_out}" \
    --plugin=protoc-gen-grpc="${grpc_plugin}" \
    "${proto_file}"

python3 -m grpc_tools.protoc \
    --proto_path="$(dirname "${proto_file}")" \
    --python_out="${python_out}" \
    --grpc_python_out="${python_out}" \
    "${proto_file}"

sed -i 's/^import maze_pb2/from . import maze_pb2/' \
    "${python_out}/maze_pb2_grpc.py"
touch "${python_out}/__init__.py"
cp "${proto_file}" "/output/maze.proto"
