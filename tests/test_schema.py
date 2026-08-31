import importlib
import os
import sys
import unittest


BINDINGS_DIR = os.environ.get("RL_CONTRACT_TEST_BINDINGS_DIR")
if not BINDINGS_DIR:
    raise RuntimeError(
        "RL_CONTRACT_TEST_BINDINGS_DIR must point to generated Python bindings"
    )
sys.path.insert(0, BINDINGS_DIR)

common_pb2 = importlib.import_module("common_pb2")
training_pb2 = importlib.import_module("training_pb2")
maze_task_pb2 = importlib.import_module("maze_task_pb2")


def round_trip(message):
    payload = message.SerializeToString(deterministic=True)
    parsed = type(message)()
    parsed.ParseFromString(payload)
    return payload, parsed


def fill_digest(digest, value):
    digest.algorithm = common_pb2.DIGEST_ALGORITHM_SHA256
    digest.hex = value


def fill_service(service, component, instance):
    service.component = component
    service.instance_id = instance
    service.lifecycle_epoch = 1


class TrainingWireTest(unittest.TestCase):
    def test_fixed_component_messages_round_trip(self):
        open_request = maze_task_pb2.OpenSessionReq()
        fill_service(open_request.client, "maze-client", "client-fixed")
        open_request.environment_instance_id = "environment-fixed"
        open_request.request_id = "open-fixed"

        update_request = maze_task_pb2.UpdateReq()
        update_request.command.session_id = "session-fixed"
        update_request.command.episode_id = "episode-fixed"
        update_request.command.session_epoch = 1
        update_request.command.sequence = 2
        update_request.frame_id = 7
        state = update_request.agents.add()
        state.agent_id = 3
        state.position.x = 4.0
        state.position.y = 5.0
        state.last_move_blocked = False
        state.executed_action_id = 2

        update_response = maze_task_pb2.UpdateRsp()
        update_response.reply.result = maze_task_pb2.COMMAND_RESULT_APPLIED
        update_response.reply.applied_sequence = 2
        update_response.reply.phase = maze_task_pb2.SESSION_PHASE_EPISODE_RUNNING
        action = update_response.action_batch.actions.add()
        action.agent_id = 3
        action.action_id = 6

        manifest = training_pb2.ModelArtifactManifest()
        manifest.identity.model_lineage_id = "lineage-fixed"
        manifest.identity.model_step = 4
        fill_digest(manifest.identity.artifact_digest, "a" * 64)
        fill_digest(manifest.identity.manifest_digest, "b" * 64)
        manifest.size_bytes = 123
        manifest.trained_samples = 456
        fill_digest(manifest.training_config_digest, "e" * 64)
        fill_digest(manifest.training_contract_digest, "c" * 64)
        manifest.published_at_unix_ms = 1_700_000_000_000
        manifest.rollout_estimator_profile.gamma = 0.99
        manifest.rollout_estimator_profile.gae_lambda = 0.95
        manifest.rollout_estimator_profile.tmax = 128
        fill_digest(
            manifest.rollout_estimator_profile.profile_digest, "f" * 64
        )

        register_model = training_pb2.RegisterModelReq()
        register_model.manifest.CopyFrom(manifest)
        register_model.contract.package_name = "rl-contracts"
        register_model.local_artifact_path = "/models/0000004/SaveModel.onnx"

        model_ack = training_pb2.AckModelReq()
        fill_service(model_ack.aiserver, "aiserver", "aiserver-fixed")
        model_ack.model.CopyFrom(manifest.identity)
        model_ack.load_instance_id = "load-fixed"
        model_ack.load_status = training_pb2.MODEL_LOAD_STATUS_LOADED

        transition = training_pb2.ProcessedTransition()
        transition.item_id = "item-fixed"
        transition.observation.extend([1.0, 2.0])
        transition.action = 6
        transition.behavior_log_probability = -0.5
        transition.behavior_value = 0.25
        transition.advantage = 0.75
        transition.value_target = 1.0
        transition.behavior_model_step = 4
        transition.created_at_unix_ms = 1_700_000_000_000

        envelope = training_pb2.ProcessedTransitionEnvelope()
        envelope.envelope_id = "envelope-fixed"
        fill_digest(envelope.payload_digest, "d" * 64)
        fill_service(envelope.producer, "aiserver", "aiserver-fixed")
        fill_digest(envelope.training_contract_digest, "c" * 64)
        envelope.behavior_model.CopyFrom(manifest.identity)
        envelope.samples.add().CopyFrom(transition)

        push_request = training_pb2.PushSamplesReq()
        push_request.envelope.CopyFrom(envelope)

        get_request = training_pb2.GetBatchReq()
        get_request.requested_transitions = 1
        get_request.timeout_ms = 10
        fill_service(get_request.consumer, "learner", "learner-fixed")
        fill_digest(get_request.required_training_contract_digest, "c" * 64)

        get_response = training_pb2.GetBatchRsp()
        get_response.items.add().transition.CopyFrom(transition)
        get_response.items[0].insert_sequence = 1
        get_response.items[0].inserted_at_unix_ms = 1_700_000_000_001
        get_response.items[0].draw_count = 1
        get_response.delivery_id = "delivery-fixed"
        get_response.result = training_pb2.GET_BATCH_RESULT_LEASED
        fill_service(get_response.sample_pool, "sample-pool", "pool-fixed")

        ack_request = training_pb2.AckBatchReq()
        fill_service(ack_request.consumer, "learner", "learner-fixed")
        ack_request.delivery_id = "delivery-fixed"
        ack_request.disposition = training_pb2.ACK_DISPOSITION_TRAINED
        ack_request.train_update_id = "update-fixed"

        messages = (
            open_request,
            update_request,
            update_response,
            manifest,
            register_model,
            model_ack,
            envelope,
            push_request,
            get_request,
            get_response,
            ack_request,
        )
        for message in messages:
            with self.subTest(message=message.DESCRIPTOR.full_name):
                payload, parsed = round_trip(message)
                self.assertGreater(len(payload), 0)
                self.assertEqual(parsed, message)

        self.assertTrue(transition.HasField("behavior_model_step"))
