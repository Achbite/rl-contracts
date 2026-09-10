#!/usr/bin/env bash

# Paths are relative to the Contracts root and remain unchanged in artifacts.
select_contract_profile() {
    local selected="$1"
    local -a training_protos=(
        proto/common/identity.proto
        proto/training/model_identity.proto
        proto/training/training.proto
        proto/metrics/registry.proto
        proto/metrics/catalog.proto
        proto/metrics/transport.proto
        proto/metrics/training.proto
    )
    local -a training_services=(
        proto/training/training.proto
        proto/metrics/catalog.proto
        proto/metrics/transport.proto
    )
    local -a task_protos=(
        proto/communication/session.proto
        proto/maze/maze.proto
        proto/maze/metrics.proto
    )
    task_service_proto_files=()
    case "${selected}" in
        training)
            proto_files=("${training_protos[@]}")
            service_proto_files=("${training_services[@]}")
            ;;
        task-maze)
            proto_files=(proto/common/identity.proto proto/metrics/registry.proto "${task_protos[@]}")
            task_service_proto_files=(proto/maze/maze.proto)
            service_proto_files=("${task_service_proto_files[@]}")
            ;;
        all)
            proto_files=("${training_protos[@]}" "${task_protos[@]}")
            task_service_proto_files=(proto/maze/maze.proto)
            service_proto_files=("${training_services[@]}" "${task_service_proto_files[@]}")
            ;;
        *)
            echo "unknown Contracts profile: ${selected}" >&2
            return 2
            ;;
    esac
}
