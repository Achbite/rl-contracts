# RL Contracts

English | [简体中文](README.md)

Canonical Protobuf contracts for the training framework. The current candidate version is
`0.8.0`. `common.proto` contains stable cross-domain identity values, `training.proto`
contains sample, sample-pool, model-distribution and typed metric contracts, and
`maze_task.proto` contains the Maze Client and Task Adapter lifecycle. A build generates
C++ and Python bindings plus a manifest binding source, artifact, platform and generator
identities.

## Build

```bash
bash build_artifact.sh
```

Output directory:

```text
../.workspace/artifacts/rl-contracts/0.8.0/<platform>/
```

If the same version already exists with different content, the build stops instead of overwriting the artifact.

## License

[MIT License](LICENSE)
