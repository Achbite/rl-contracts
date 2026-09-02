#!/usr/bin/env bash

set -euo pipefail

profile="${1:-all}"
if [ "$#" -gt 1 ]; then
    echo "usage: generate-contracts [training|task-maze|all]" >&2
    exit 2
fi

proto_dir="/source/proto/v1"
cpp_out="/output/cpp"
python_out="/output/python"

case "${profile}" in
    training)
        proto_files=(
            "${proto_dir}/common.proto"
            "${proto_dir}/training.proto"
            "${proto_dir}/training_metrics.proto"
        )
        service_proto_files=("${proto_dir}/training.proto")
        ;;
    task-maze)
        proto_files=(
            "${proto_dir}/common.proto"
            "${proto_dir}/maze_task.proto"
            "${proto_dir}/maze_metrics.proto"
        )
        service_proto_files=("${proto_dir}/maze_task.proto")
        ;;
    all)
        proto_files=(
            "${proto_dir}/common.proto"
            "${proto_dir}/training.proto"
            "${proto_dir}/maze_task.proto"
            "${proto_dir}/maze_metrics.proto"
            "${proto_dir}/training_metrics.proto"
        )
        service_proto_files=(
            "${proto_dir}/training.proto"
            "${proto_dir}/maze_task.proto"
        )
        ;;
    *)
        echo "unknown Contracts generation profile: ${profile}" >&2
        exit 2
        ;;
esac

for proto_file in "${proto_files[@]}"; do
    test -f "${proto_file}"
done
mkdir -p "${cpp_out}" "${python_out}"

grpc_plugin="$(command -v grpc_cpp_plugin)"
protoc \
    --proto_path="${proto_dir}" \
    --cpp_out="${cpp_out}" \
    "${proto_files[@]}"
protoc \
    --proto_path="${proto_dir}" \
    --grpc_out="${cpp_out}" \
    --plugin=protoc-gen-grpc="${grpc_plugin}" \
    "${service_proto_files[@]}"

python3 -m grpc_tools.protoc \
    --proto_path="${proto_dir}" \
    --python_out="${python_out}" \
    "${proto_files[@]}"
python3 -m grpc_tools.protoc \
    --proto_path="${proto_dir}" \
    --grpc_python_out="${python_out}" \
    "${service_proto_files[@]}"

for generated in "${python_out}"/*_pb2.py "${python_out}"/*_pb2_grpc.py; do
    sed -i \
        -e 's/^import common_pb2/from . import common_pb2/' \
        -e 's/^import training_pb2/from . import training_pb2/' \
        -e 's/^import maze_task_pb2/from . import maze_task_pb2/' \
        -e 's/^import maze_metrics_pb2/from . import maze_metrics_pb2/' \
        -e 's/^import training_metrics_pb2/from . import training_metrics_pb2/' \
        "${generated}"
done
touch "${python_out}/__init__.py"
cp "${proto_files[@]}" "/output/"
# Generated artifacts are bind-mounted into development containers. Docker's
# user-namespace mapping must not depend on the host file owner to read them.
find /output -type f -exec chmod 0644 {} +
find /output -type d -exec chmod 0755 {} +
