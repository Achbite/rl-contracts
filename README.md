# RL Contracts

简体中文 | [English](README.en.md)

训练框架的 Protobuf 契约仓库，当前版本为 `0.6.0`。构建后生成 C++、Python bindings 和对应的 checksum manifest。

## 构建

```bash
bash build_artifact.sh
```

输出目录：

```text
../.workspace/artifacts/rl-contracts/0.6.0/<platform>/
```

相同版本已经存在但内容不一致时，构建会停止，不会覆盖已有制品。

## License

[MIT License](LICENSE)
