# RL Contracts

简体中文 | [English](README.en.md)

## 1. 运行测试

```bash
bash ./test.sh
```

`test.sh` 是本仓库的统一测试入口，并按显式清单运行当前开发校验。

## 2. 生成 0.15.0 制品

从当前源码生成训练协议与 Maze 任务协议两个独立源码制品：

```bash
bash build_artifact.sh
```

输出：

```text
../.workspace/artifacts/rl-contracts/0.15.0/training/
../.workspace/artifacts/rl-contracts/0.15.0/task-maze/
```

也可以只生成一个明确目标：

```bash
bash build_artifact.sh training
bash build_artifact.sh task-maze
```

`training/` 包含任务无关的训练、样本池、模型分发和训练指标 bindings；`task-maze/` 包含
Client↔AIServer Maze RPC、Maze Episode 指标与当前 Maze TrainingContract。二者都是生成源码，
不以 Docker 平台作为兼容或同步门禁。Sample Pool 与 Model Distributor 的二进制制品仍由各自
仓库记录真实构建平台。构建入口使用临时目录完成后再替换同版本输出；Git clean/dirty 与源码哈希
不作为生成门禁。

## 3. 同步消费者

普通构建与 `make shell` 都不会同步协议。需要明确采用此仓的 Maze 协议 release 时，从 Framework
执行一次显式同步并审查各消费者仓的 diff：

```bash
(cd ../rl-framework && bash sync_maze_protocol.sh)
```

训练协议制品只作为 Sample Pool/Model Distributor 的构建输入；Learner 运行时二进制由独立制品
脚本同步。运行通信由 Proto/TrainingContract 的业务字段和 digest 决定，不要求各仓源码、生成器、
构建哈希或平台值相等。

## License

[MIT License](LICENSE)
