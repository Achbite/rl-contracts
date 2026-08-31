# RL Contracts

[简体中文](README.md) | English

## 1. Run tests

```bash
bash ./test.sh
```

`test.sh` is the repository's unified test entrypoint and runs the current
development checks from an explicit allowlist.

## 2. Create the 0.15.0 artifact

Before this version is created for the first time, the repository must be reviewed, committed, and clean:

```bash
bash build_artifact.sh
```

Output:

```text
../.workspace/artifacts/rl-contracts/0.15.0/<platform>/
```

The artifact contains C++ and Python bindings, all three Proto files, the `maze.metrics` schema, its digest, and the manifest. Existing content under the same version is never overwritten when identities differ.

## 3. Sync consumers

```bash
(cd ../rl-aiserver && bash scripts/sync_contract_snapshot.sh)
(cd ../maze-client && bash scripts/sync_contract_snapshot.sh)
```

Learner consumes the fixed artifact directly when its image or development container is created.

## License

[MIT License](LICENSE)
