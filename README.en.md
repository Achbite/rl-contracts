# RL Contracts

English | [简体中文](README.md)

Canonical Protobuf contracts for the training framework. The current version is `0.3.0`. The build produces C++ and Python bindings with a checksum manifest.

## Build

```bash
bash build_artifact.sh
```

Output directory:

```text
../.workspace/artifacts/rl-contracts/0.3.0/<platform>/
```

If the same version already exists with different content, the build stops instead of overwriting the artifact.

## License

[MIT License](LICENSE)
