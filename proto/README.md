# Protocol layout

The Contracts repository owns the source definitions. Category paths are kept
in generated C++ / Python packages, artifacts, and consumer snapshots, without
numbered version directories.

| Directory | Responsibility |
| --- | --- |
| `common/` | Cross-component identity and common result values. |
| `communication/` | Shared Session, command identity, reply and lifecycle used by typed task RPCs. |
| `training/` | Task-neutral samples, delivery, model identity/distribution and component business status. |
| `metrics/registry.proto` | Registered metric definitions, values, aggregation and sum/count records. |
| `metrics/catalog.proto` | Independent read-only field discovery. |
| `metrics/transport.proto` | Opaque metric events, batches, cursors, gaps, final and ACK. |
| `metrics/training.proto` | Learner-owned Train Update measurements. |
| `tasks/maze/task.proto` | Maze environment, observation/action, task outcomes and typed Maze RPCs. |
| `tasks/maze/metrics.proto` | Maze-owned Episode calculation facts. |

Task RPCs import common identity and communication lifecycle types. Shared
metric registry, catalog and transport do not import task or training RPCs.
Learner measurements import only model identity and metric value types. Maze
measurements import metric value types, independently of the training service.

Generation profiles are declared in `scripts/profiles.sh`. The training profile
does not contain task or Client Session bindings. The task-maze artifact includes
the Maze measurements and their registry dependency; the Client snapshot selects
only common identity, communication lifecycle, Maze task RPC and SDK headers.
AIServer combines the task and training profiles.

Build with `bash ./build_artifact.sh all` from the repository root. For a source
`proto/metrics/catalog.proto`, output paths are:

```text
proto/metrics/catalog.proto
cpp/proto/metrics/catalog.pb.{h,cc}
cpp/proto/metrics/catalog.grpc.pb.{h,cc}
python/proto/metrics/catalog_pb2.py
python/proto/metrics/catalog_pb2_grpc.py
```

Use the artifact `cpp/` directory as the C++ include root and `python/` as the
Python package root. Repository-local snapshots preserve these category paths.
Edit definitions here, then explicitly generate and sync consumers; do not edit
generated bindings. Directory names classify ownership; protobuf package names,
field numbers and service method names retain their current wire meaning.

The current build writes to `.workspace/artifacts/rl-contracts/<profile>/`;
the development channel writes to
`.workspace/dev-artifacts/rl-contracts/<profile>/current/`. Consumers use the
profile path directly. Build image tags remain traceability metadata and do not
select a protocol directory.
