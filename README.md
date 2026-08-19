# RL Contracts

简体中文 | [English](README.en.md)

## 1. 运行测试

```bash
bash ./test.sh
```

`test.sh` 是本仓库唯一公开测试入口；测试文件和测试项使用显式清单，新增或扩写测试必须先有用户批准的 TCR。

## 2. 生成 0.13.0 制品

首次生成该版本前，仓库必须是已经审核并提交的 clean Git 保存点：

```bash
bash build_artifact.sh
```

输出：

```text
../.workspace/artifacts/rl-contracts/0.13.0/<platform>/
```

制品包含 C++/Python bindings、三个 Proto、`maze.metrics.v3` schema、digest 和 manifest。相同版本内容不一致时不会覆盖旧制品。

## 3. 同步消费者

```bash
(cd ../rl-aiserver && bash scripts/sync_contract_snapshot.sh)
(cd ../maze-client && bash scripts/sync_contract_snapshot.sh)
```

Learner 在构建镜像和开发容器时直接使用该固定版本制品。

## License

[MIT License](LICENSE)
