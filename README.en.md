# RL Contracts

[简体中文](README.md) | English

## 1. Run tests

```bash
bash ./test.sh
```

`test.sh` is the repository's unified test entrypoint and runs the current
development checks from an explicit allowlist.

## 2. Create the 0.15.0 artifact

Build independent training-wire and Maze task-protocol source artifacts:

```bash
bash build_artifact.sh
```

Output:

```text
../.workspace/artifacts/rl-contracts/0.15.0/training/
../.workspace/artifacts/rl-contracts/0.15.0/task-maze/
```

Build either target explicitly when only one is needed:

```bash
bash build_artifact.sh training
bash build_artifact.sh task-maze
```

`training/` contains task-neutral training, Sample Pool, model-distribution, and
training-metric bindings. `task-maze/` contains the Client-AIServer Maze RPC and
Maze Episode metrics. Both are generated source
artifacts and do not use the Docker platform as a compatibility or synchronization
gate. The Sample Pool and Model Distributor binary artifacts still record their
real build platform. Each build stages into a temporary directory before replacing
the same-version output. Git state and source hashes are not generation gates.

## 3. Sync consumers

Normal builds and `make shell` never synchronize protocols. When a checkout is
intentionally adopting this repository's Maze release, run the explicit Framework
entrypoint and review the resulting consumer diffs:

```bash
(cd ../rl-framework && bash sync_maze_protocol.sh)
```

When the task-neutral training protocol must be adopted explicitly, run:

```bash
(cd ../rl-framework && bash sync_training_protocol.sh)
```

The training protocol is the shared Proto input for Sample Pool, Model Distributor,
AIServer, and Learner. The Sample Pool and Model Distributor binaries required by
Learner are still staged by their separate artifact command. Runtime communication is
governed only by Proto business fields, service lifecycles, object identities, and
sequence/ACK semantics, not repository source, generator, version, digest, or platform
equality.

## License

[MIT License](LICENSE)
