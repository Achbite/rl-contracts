#include "rl_sdk/task_client.h"
#include "proto/example/task.sdk.pb.h"
#include <iostream>
namespace task = sdk::example;
int main(int argc, char** argv) {
    if (argc != 2) return 1;
    rl_sdk::TaskClient<task::ExampleServiceProtocol> client;
    const auto applied = rl_sdk::CommandOutcome::Applied;
    task::OpenSessionRsp open; task::InitRsp init; task::BeginEpisodeRsp begin;
    if (!client.Connect(argv[1]) || client.OpenSession(open) != applied ||
        client.Init({}, init) != applied || client.BeginEpisode(begin) != applied) {
        std::cerr << client.error(); return 2;
    }
    task::UpdateReq req; task::UpdateRsp rsp;
    req.mutable_state()->set_observation(4.25); req.mutable_state()->set_label("task-fact");
#ifdef WITH_EXTRA_FIELD
    req.mutable_state()->set_revision(41);
#endif
    if (client.Update(req, rsp) != applied || rsp.state().observation() != 6.75 || rsp.state().label() != "task-fact-server") return 3;
#ifdef WITH_EXTRA_FIELD
    if (rsp.state().revision() != 42) return 4;
#endif
    task::EndEpisodeRsp end; task::CloseSessionRsp close;
    if (client.EndEpisode(end) != applied || client.CloseSession(close) != applied) return 5;
    std::cout << "independent typed SDK round-trip: PASS\n";
    return 0;
}
