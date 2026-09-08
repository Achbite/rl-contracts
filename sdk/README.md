# C++ Client SDK

公共源码由训练组维护，随现有 `rl-contracts` artifact 交付；没有独立服务进程。
`proto/communication/session.proto` 声明通用命令身份、回复及生命周期。任务的 observation、action、初始化和结果继续使用 `proto/tasks/<任务名>/` 下自己的强类型 Proto / RPC。

## 交付与依赖

- `include/rl_sdk/session.h`：一个 Session cursor、强类型命令确认、WAIT，以及 `RunSession` / `RunEpisode` 完整流程。
- `include/rl_sdk/transport.h`：gRPC channel、连接、deadline 及现有 exact retry。
- `include/rl_sdk/server_command.h` / `replay_window.h`：AIServer 的命令验证、提交及重放窗口；任务验证仍在任务 Binding。
- `include/rl_sdk/metric_catalog.h`：组件目录服务的 C++ 组装，不依赖 Client SDK 的 Session。

依赖 C++17、Protobuf、gRPC、pthread。在本仓执行 `bash ./build_artifact.sh all`，现有 training / task artifact 中同时交付 `sdk/` 及 `cpp/rl_sdk/`。生成代码和 SDK 头文件在同一合同批次生成、同步；源码 commit 和包版本用于追溯。

独立 CMake 项目可以使用：

```cmake
add_subdirectory(${CONTRACT_ARTIFACT}/sdk rl-sdk)
add_library(task_binding STATIC
  task_binding.cpp
  ${CONTRACT_ARTIFACT}/cpp/proto/common/identity.pb.cc
  ${CONTRACT_ARTIFACT}/cpp/proto/communication/session.pb.cc
  ${CONTRACT_ARTIFACT}/cpp/proto/tasks/your_task/task.pb.cc
  ${CONTRACT_ARTIFACT}/cpp/proto/tasks/your_task/task.grpc.pb.cc)
target_include_directories(task_binding PUBLIC ${CONTRACT_ARTIFACT}/cpp)
target_link_libraries(task_binding PUBLIC rl_sdk::sdk)
```

其中 `your_task` 为任务组与训练组约定的 Proto。项目当前可编译示例是 `maze-client` 的 `maze_client_binding` 库和 `maze_client` 程序；各仓根级 `build.sh` 构建，根级 `test.sh` 执行已登记验证。

## 环境团队的最小接入

Maze Binding 头文件为 `maze-client/src/task/maze_client_binding.h`，环境实现为 `MazeEnv`。训练组提供 Binding，环境团队实现并维护环境方法及其协议事实映射。

```cpp
#include "task/maze_client_binding.h"
#include "config/config_loader.h"
#include "env/maze_env.h"

rl_sdk::CommandOutcome RunEnvironment(const ClientConfig& configuration) {
    MazeEnv environment;
    MazeClientBinding binding(configuration, environment);
    return binding.Run();
}
```

完整配置加载、日志与信号接线见 `RunMazeClient`。通信流程由 SDK 调用，环境代码不应再写 Open/Begin/End 重试循环。

新增任务时，训练组实现对应 Binding：`Open`、`Initialize`、`Begin`、`RunEpisode`、`End`、`Abort`、`Close`，以及 `Active`、`CanClose`、`Complete`、`Stopped` 状态查询。Binding 使用任务生成 Stub；公共 `RunSession(binding)` 决定调用顺序。这里是编译期接口，不是一个统一 envelope service。

在动作循环中，Binding 把四种任务操作交给 `RunEpisode`：生成当前事实、提交并验证回复、判断终止、执行已确认动作。流程先提交 Reset 后事实，每次动作之后提交执行结果，最后一次结果仍提交，最终回复不再驱动额外动作。

## 命令与退出语义

`Session::Prepare` 填入当前 identity，不推进 cursor。`Session::Exchange` 只在任务回复通过验证且服务器确认 APPLIED / ALREADY_APPLIED 时推进一次；WAIT 复用同一不可变 request。Transport 仅按原合同对指定 gRPC 状态最多尝试两次，间隔 50 ms；任务 RPC 保留原 deadline。

返回结果包括 `Applied`、`Rejected`、`Unknown`、`Stopped`、`WaitExpired`。Unknown 不进入替代 Abort/Close，避免覆盖一个尚未确认的命令。明确未应用的 WAIT / REJECTED 依现有生命周期结束；取消和 Abort WAIT 的预算由原调用合同提供。SDK 不增加跨进程 Session 恢复，也不对断链承诺最终送达。

SDK 不计算训练 reward、GAE、ProcessedTransition，不连接 Learner / Pool / Distributor。任务终止、截断及 bootstrap 仍由任务合同和 AIServer 解释。第二任务接入属于单独的 S3 批次。
