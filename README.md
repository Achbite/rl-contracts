# RL Contracts

简体中文 | [English](README.en.md)

Proto 按 `common / communication / training / metrics / tasks/<任务名>` 分类，
不设置固定版本编号目录；生成代码、制品与消费者快照保留相同分类结构。
具体职责和依赖见 [Proto 目录说明](proto/README.md)。公共通信与指标协议不放入任务 Proto。

## 1. 运行测试

```bash
bash ./test.sh
```

`test.sh` 是本仓库的统一测试入口，并按显式清单运行当前开发校验。

## 2. 生成当前制品

从当前源码生成训练协议与 Maze 任务协议两个独立源码制品：

```bash
bash build_artifact.sh
```

输出：

```text
../.workspace/artifacts/rl-contracts/training/
../.workspace/artifacts/rl-contracts/task-maze/
```

也可以只生成一个明确目标：

```bash
bash build_artifact.sh training
bash build_artifact.sh task-maze
```

`training/` 包含任务无关的训练、样本池、模型分发和训练指标 bindings；`task-maze/` 包含
Client↔AIServer Maze RPC 与 Maze Episode 指标。二者都是生成源码，
不以 Docker 平台作为兼容或同步门禁。Sample Pool 与 Model Distributor 的二进制制品仍由各自
仓库记录真实构建平台。构建入口使用临时目录完成后再替换对应 profile 的当前输出；Git clean/dirty 与源码哈希
不作为生成门禁。

## 3. 同步消费者

普通构建与 `make shell` 都不会同步协议。需要明确采用此仓的 Maze 协议 release 时，从 Framework
执行一次显式同步并审查各消费者仓的 diff：

```bash
(cd ../rl-framework && bash sync_maze_protocol.sh)
```

任务无关的训练协议需要明确更新时，执行：

```bash
(cd ../rl-framework && bash sync_training_protocol.sh)
```

训练协议是 Sample Pool、Model Distributor、AIServer 与 Learner 的共同 Proto 输入；Learner 所需的
Sample Pool/Model Distributor 二进制仍由独立制品脚本装配。运行通信只由 Proto 中的业务字段、
服务生命周期、对象身份和序列/ACK 语义决定，不要求各仓源码、生成器、版本、摘要或平台值相等。

## License

[MIT License](LICENSE)
