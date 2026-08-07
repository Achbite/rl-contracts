# RL Contracts

简体中文 | [English](README.en.md)

训练框架的 Protobuf 契约仓库，当前候选版本为 `0.9.1`：

- `common.proto`：跨域稳定身份与 digest 值对象。
- `training.proto`：Sample、Sample Pool、模型分发与类型化指标信封。
- `maze_task.proto`：Maze Client 与 Task Adapter 的任务及生命周期协议。

构建后生成 C++、Python bindings 和同时绑定 source、artifact、platform、generator
身份的 manifest。

## 构建

```bash
bash build_artifact.sh
```

输出目录：

```text
../.workspace/artifacts/rl-contracts/0.9.1/<platform>/
```

相同版本已经存在但内容不一致时，构建会停止，不会覆盖已有制品。

## License

[MIT License](LICENSE)
