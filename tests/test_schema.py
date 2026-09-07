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

training_pb2 = importlib.import_module("training_pb2")
maze_task_pb2 = importlib.import_module("maze_task_pb2")
maze_metrics_pb2 = importlib.import_module("maze_metrics_pb2")
training_metrics_pb2 = importlib.import_module("training_metrics_pb2")

def round_trip(message):
    payload = message.SerializeToString(deterministic=True)
    parsed = type(message)()
    parsed.ParseFromString(payload)
    return payload, parsed


def fill_service(service, component, instance):
    service.component = component
    service.instance_id = instance
    service.lifecycle_epoch = 1


class TaskProtocolContractTest(unittest.TestCase):
    def test_task_protocol_map_and_mask_round_trip(self):
        request = maze_task_pb2.OpenSessionReq()
        fill_service(request.client, "maze-client", "client-instance")
        request.environment_instance_id = "environment-instance"
        request.request_id = "request-id"
        response = maze_task_pb2.OpenSessionRsp()
        response.environment.agent_count = 2
        response.environment.map_id = "170001"
        response.environment.episode_max_steps = 128
        response.environment.action_mask_mode = (
            maze_task_pb2.ACTION_MASK_MODE_REQUIRED
        )

        init_request = maze_task_pb2.InitReq()
        init_request.map.map_id = response.environment.map_id
        init_request.map.grid_columns = 2
        init_request.map.grid_rows = 2
        init_request.map.grid_size_microunits = 1_000_000
        init_request.map.goal_grid_x = 1
        init_request.map.goal_grid_y = 1
        init_request.map.blocked_bitmap = b"\x00"

        update_request = maze_task_pb2.UpdateReq()
        state = update_request.agents.add()
        state.agent_id = 0
        state.executed_action_id = maze_task_pb2.MAZE_ACTION_RIGHT
        action_values = maze_task_pb2.MazeAction.DESCRIPTOR.values
        state.action_mask.extend(
            value.number != maze_task_pb2.MAZE_ACTION_LEFT
            for value in action_values
        )

        update_response = maze_task_pb2.UpdateRsp()
        action = update_response.action_batch.actions.add()
        action.agent_id = state.agent_id
        action.action_id = maze_task_pb2.MAZE_ACTION_RIGHT

        for message in (request, response, init_request, update_request, update_response):
            with self.subTest(message=message.DESCRIPTOR.full_name):
                payload, parsed = round_trip(message)
                self.assertGreater(len(payload), 0)
                self.assertEqual(parsed, message)

        self.assertEqual(response.environment.map_id, init_request.map.map_id)
        self.assertEqual(len(state.action_mask), len(action_values))
        self.assertTrue(state.action_mask[action.action_id])

    def test_abort_wait_is_explicit(self):
        response = maze_task_pb2.AbortEpisodeRsp()
        response.reply.result = maze_task_pb2.COMMAND_RESULT_WAIT
        response.reply.applied_sequence = 7
        response.wait.retry_after_ms = 25
        _, parsed = round_trip(response)
        self.assertEqual(parsed.reply.result, maze_task_pb2.COMMAND_RESULT_WAIT)
        self.assertEqual(parsed.reply.applied_sequence, 7)
        self.assertEqual(parsed.wait.retry_after_ms, 25)


class TrainingTransportContractTest(unittest.TestCase):
    def test_transition_preserves_object_identity_and_opaque_mask(self):
        transition = training_pb2.ProcessedTransition()
        transition.item_id = "item-id"
        transition.observation.extend([1.0, 2.0, 3.0])
        transition.action = 1
        transition.behavior_log_probability = -0.5
        transition.behavior_value = 0.25
        transition.advantage = 0.75
        transition.value_target = 1.0
        transition.behavior_model_step = 0
        transition.created_at_unix_ms = 1_700_000_000_000
        transition.action_mask.extend([True, True, False, True])

        envelope = training_pb2.ProcessedTransitionEnvelope()
        envelope.envelope_id = "envelope-id"
        fill_service(envelope.producer, "aiserver", "aiserver-instance")
        envelope.behavior_model.model_lineage_id = "lineage-id"
        envelope.behavior_model.model_step = 0
        envelope.samples.add().CopyFrom(transition)

        _, parsed = round_trip(envelope)
        self.assertEqual(parsed, envelope)
        self.assertTrue(parsed.samples[0].HasField("behavior_model_step"))
        self.assertEqual(
            list(parsed.samples[0].action_mask), list(transition.action_mask)
        )

    def test_metric_transport_keeps_fact_kind_payload_opaque(self):
        record = training_pb2.RegisteredMetricRecord()
        record.definitions.add(
            metric_id="task.balance.reward", display_name="Balance reward", unit="reward",
            scope="episode", value_type=training_pb2.METRIC_VALUE_TYPE_SUM_COUNT,
            aggregation=training_pb2.METRIC_AGGREGATION_MEAN, denominator="transition",
        )
        point = record.points.add(metric_id="task.balance.reward")
        point.sum_count.sum = 1.25
        point.sum_count.count = 2
        record.definitions.add(
            metric_id="update.sequence", display_name="Update", unit="count", scope="update",
            value_type=training_pb2.METRIC_VALUE_TYPE_UNSIGNED,
            aggregation=training_pb2.METRIC_AGGREGATION_LATEST,
        )
        record.points.add(metric_id="update.sequence", unsigned_value=(1 << 64) - 1)
        batch = training_pb2.MetricBatch()
        event = batch.events.add(
            event_sequence=1, observed_at_unix_ms=1700000000000,
            fact_kind=training_pb2.METRIC_FACT_KIND_REGISTERED_METRICS,
            fact_payload=record.SerializeToString(deterministic=True),
        )
        _, parsed = round_trip(batch)
        self.assertEqual(parsed.events[0].fact_payload, event.fact_payload)
        self.assertEqual(training_pb2.RegisteredMetricRecord.FromString(parsed.events[0].fact_payload), record)

    def test_model_registration_does_not_imply_artifact_layout(self):
        request = training_pb2.RegisterModelReq()
        request.local_artifact_path = "/configured-model-root/published-model.onnx"
        request.manifest.identity.model_lineage_id = "lineage-id"
        request.manifest.identity.model_step = 7
        request.manifest.size_bytes = 123
        request.manifest.trained_samples = 456

        _, parsed = round_trip(request)
        self.assertEqual(parsed, request)
if __name__ == "__main__":
    unittest.main()
