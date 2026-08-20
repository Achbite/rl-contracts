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


class A3DevelopmentWireTest(unittest.TestCase):
    def test_fixed_component_messages_round_trip(self):
        open_request = maze_task_pb2.OpenSessionReq()
        fill_service(open_request.client, "maze-client", "client-fixed")
        open_request.environment_instance_id = "environment-fixed"
        open_request.supported_session_protocol_versions.append(3)
        open_request.idempotency_key = "open-fixed"

        update_request = maze_task_pb2.UpdateReq()
        update_request.command.session_id = "session-fixed"
        update_request.command.episode_id = "episode-fixed"
        update_request.command.lifecycle_epoch = 1
        update_request.command.command_sequence = 2
        update_request.command.idempotency_key = "update-fixed"
        update_request.frame_id = 7
        state = update_request.agents.add()
        state.agent_id = 3
        state.position.x = 4.0
        state.position.y = 5.0
        state.last_move_blocked = False
        state.executed_action_id = 2

        update_response = maze_task_pb2.UpdateRsp()
        update_response.lifecycle.ret_code = 0
        update_response.lifecycle.applied_sequence = 2
        action = update_response.actions.add()
        action.agent_id = 3
        action.action_id = 6

        manifest = training_pb2.ModelArtifactManifest()
        manifest.manifest_schema_version = 3
        manifest.identity.model_lineage_id = "lineage-fixed"
        manifest.identity.model_step = 4
        fill_digest(manifest.identity.artifact_digest, "a" * 64)
        fill_digest(manifest.identity.manifest_digest, "b" * 64)
        manifest.model_file = "SaveModel.onnx"
        manifest.ready = True

        model_ack = training_pb2.AckModelReq()
        fill_service(model_ack.aiserver, "aiserver", "aiserver-fixed")
        model_ack.model.CopyFrom(manifest.identity)
        model_ack.load_instance_id = "load-fixed"
        model_ack.load_status = training_pb2.MODEL_LOAD_STATUS_LOADED

        transition = training_pb2.ProcessedTransition()
        transition.item_id = "item-fixed"
        transition.environment_session_id = "session-fixed"
        transition.episode_id = "episode-fixed"
        transition.agent_id = 3
        transition.segment_id = "segment-fixed"
        transition.transition_index = 0
        transition.segment_transition_count = 1
        transition.action_step = 7
        transition.observation.extend([1.0, 2.0])
        transition.next_observation.extend([2.0, 3.0])
        transition.action = 6
        transition.reward = 0.0
        transition.behavior_log_probability = -0.5
        transition.behavior_value = 0.25
        transition.advantage = 0.75
        transition.value_target = 1.0
        transition.segment_boundary = True
        transition.bootstrap_applied = True
        transition.bootstrap_value = 0.4
        transition.behavior_policy.model_lineage_id = "lineage-fixed"
        transition.behavior_policy.model_step = 4
        fill_digest(
            transition.rollout_estimator_profile_digest,
            "c" * 64,
        )

        envelope = training_pb2.ProcessedTransitionEnvelope()
        envelope.envelope_id = "envelope-fixed"
        fill_digest(envelope.payload_digest, "d" * 64)
        envelope.transitions.add().CopyFrom(transition)
        fill_service(envelope.producer, "aiserver", "aiserver-fixed")

        push_request = training_pb2.PushSamplesReq()
        push_request.envelope.CopyFrom(envelope)

        get_request = training_pb2.GetBatchReq()
        get_request.requested_transitions = 1
        get_request.timeout_ms = 10
        fill_service(get_request.consumer, "learner", "learner-fixed")

        get_response = training_pb2.GetBatchRsp()
        get_response.items.add().transition.CopyFrom(transition)
        get_response.delivery_id = "delivery-fixed"
        get_response.returned_transitions = 1
        get_response.actual_transition_count = 1
        get_response.leased_transitions = 1
        get_response.result = training_pb2.GET_BATCH_RESULT_LEASED

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

        self.assertTrue(transition.HasField("bootstrap_value"))
        self.assertTrue(transition.behavior_policy.HasField("model_step"))
