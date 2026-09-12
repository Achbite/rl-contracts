#include "proto/example/task.grpc.pb.h"
#include <grpcpp/grpcpp.h>
#include <atomic>
#include <fstream>
#include <iostream>
#include <thread>
namespace task = sdk::example;
namespace session = rl::session::v1;
class Service final : public task::ExampleService::Service {
public:
    std::atomic<bool> closed{false};
    static void Reply(uint64_t seq, session::SessionPhase phase, session::CommandReply* reply) {
        reply->set_result(session::COMMAND_RESULT_APPLIED);
        reply->set_applied_sequence(seq);
        reply->set_phase(phase);
    }
    grpc::Status OpenSession(grpc::ServerContext*, const task::OpenSessionReq*, task::OpenSessionRsp* rsp) override {
        rsp->set_session_id("independent-session"); rsp->set_session_epoch(1);
        rsp->mutable_aiserver()->set_component("aiserver");
        rsp->mutable_aiserver()->set_instance_id("independent-server");
        rsp->mutable_aiserver()->set_lifecycle_epoch(1);
        Reply(0, session::SESSION_PHASE_OPEN, rsp->mutable_reply());
        return grpc::Status::OK;
    }
    grpc::Status Init(grpc::ServerContext*, const task::InitReq* req, task::InitRsp* rsp) override {
        Reply(req->command().sequence(), session::SESSION_PHASE_READY, rsp->mutable_reply()); return grpc::Status::OK;
    }
    grpc::Status BeginEpisode(grpc::ServerContext*, const task::BeginEpisodeReq* req, task::BeginEpisodeRsp* rsp) override {
        rsp->mutable_assignment()->set_episode_id("episode");
        Reply(req->command().sequence(), session::SESSION_PHASE_EPISODE_RUNNING, rsp->mutable_reply()); return grpc::Status::OK;
    }
    grpc::Status Update(grpc::ServerContext*, const task::UpdateReq* req, task::UpdateRsp* rsp) override {
        *rsp->mutable_state() = req->state();
        rsp->mutable_state()->set_observation(req->state().observation() + 2.5);
        rsp->mutable_state()->set_label(req->state().label() + "-server");
#ifdef WITH_EXTRA_FIELD
        rsp->mutable_state()->set_revision(req->state().revision() + 1);
#endif
        Reply(req->command().sequence(), session::SESSION_PHASE_EPISODE_TERMINAL, rsp->mutable_reply()); return grpc::Status::OK;
    }
    grpc::Status EndEpisode(grpc::ServerContext*, const task::EndEpisodeReq* req, task::EndEpisodeRsp* rsp) override {
        Reply(req->command().sequence(), session::SESSION_PHASE_READY, rsp->mutable_reply()); return grpc::Status::OK;
    }
    grpc::Status CloseSession(grpc::ServerContext*, const task::CloseSessionReq* req, task::CloseSessionRsp* rsp) override {
        Reply(req->command().sequence(), session::SESSION_PHASE_CLOSED, rsp->mutable_reply()); closed = true; return grpc::Status::OK;
    }
};
int main(int argc, char** argv) {
    if (argc != 2) return 1;
    Service service; int port = 0;
    grpc::ServerBuilder builder;
    builder.AddListeningPort("127.0.0.1:0", grpc::InsecureServerCredentials(), &port);
    builder.RegisterService(&service);
    auto server = builder.BuildAndStart();
    if (!server || !port) return 2;
    { std::ofstream output(argv[1]); output << port; }
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    while (!service.closed && std::chrono::steady_clock::now() < deadline)
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    server->Shutdown(); server->Wait();
    return service.closed ? 0 : 3;
}
