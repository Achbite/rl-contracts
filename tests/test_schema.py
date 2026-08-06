import re
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
COMMON_PROTO = REPOSITORY / "proto" / "v1" / "common.proto"
TRAINING_PROTO = REPOSITORY / "proto" / "v1" / "training.proto"
MAZE_TASK_PROTO = REPOSITORY / "proto" / "v1" / "maze_task.proto"


def without_comments(source: str) -> str:
    source = re.sub(r"//.*", "", source)
    return re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)


def block(source: str, kind: str, name: str) -> str:
    match = re.search(
        rf"\b{kind}\s+{re.escape(name)}\s*\{{(.*?)^\}}",
        source,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"{kind} {name} is missing")
    return match.group(1)


class ContractSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common = COMMON_PROTO.read_text(encoding="utf-8")
        cls.training = TRAINING_PROTO.read_text(encoding="utf-8")
        cls.task = MAZE_TASK_PROTO.read_text(encoding="utf-8")
        cls.common_code = without_comments(cls.common)
        cls.training_code = without_comments(cls.training)
        cls.task_code = without_comments(cls.task)

    def test_contract_version_is_locked_breaking_release(self):
        self.assertEqual(
            (REPOSITORY / "VERSION").read_text(encoding="utf-8").strip(),
            "0.8.0",
        )

    def test_packages_and_import_dag_are_exact(self):
        self.assertRegex(self.common_code, r"\bpackage\s+rl\.common\.v1\s*;")
        self.assertRegex(self.training_code, r"\bpackage\s+rl\.training\.v1\s*;")
        self.assertRegex(self.task_code, r"\bpackage\s+rl\.task\.maze\.v1\s*;")
        self.assertNotRegex(self.common_code, r"\bimport\s+")
        self.assertEqual(
            re.findall(r'\bimport\s+"([^"]+)"\s*;', self.training_code),
            ["common.proto"],
        )
        self.assertEqual(
            re.findall(r'\bimport\s+"([^"]+)"\s*;', self.task_code),
            ["common.proto"],
        )
        for source in (self.common_code, self.training_code, self.task_code):
            self.assertNotRegex(source, r"\bpackage\s+maze\s*;")

    def test_common_is_a_strict_value_object_whitelist(self):
        declarations = set(
            re.findall(r"\b(?:message|enum|service)\s+([A-Za-z0-9_]+)", self.common_code)
        )
        self.assertEqual(
            declarations,
            {
                "OperationResult",
                "DigestAlgorithm",
                "ContentDigest",
                "ContractIdentity",
                "SchemaIdentity",
                "ServiceInstanceIdentity",
            },
        )
        self.assertNotRegex(self.common_code, r"\bservice\s+")

    def test_task_does_not_import_or_redeclare_training_contracts(self):
        for training_type in (
            "Sample",
            "SampleBatch",
            "BehaviorPolicyIdentity",
            "TrainingSemanticsIdentity",
            "ModelArtifactManifest",
            "SampleDistributorService",
            "ModelDistributorService",
            "MetricDescriptor",
        ):
            self.assertNotRegex(self.task_code, rf"\b{training_type}\b")

    def test_training_has_no_maze_task_semantics(self):
        for forbidden in (
            "MapDescriptor",
            "TaskIdentity",
            "MazeTaskSpec",
            "CurriculumStage",
            "MazeTerminationReason",
            "EpisodeMode",
            "WorkloadMode",
            "ReplayPolicy",
            "GOAL_REACHED",
            "TIME_LIMIT",
            "ASTAR",
            "reward_details",
        ):
            self.assertNotRegex(self.training_code, rf"\b{forbidden}\b")

    def test_open_session_is_capability_negotiation_only(self):
        request = block(self.task_code, "message", "OpenSessionReq")
        response = block(self.task_code, "message", "OpenSessionRsp")
        for forbidden in (
            "session_id",
            "episode_id",
            "agent_count",
            "agent_num",
            "map_id",
            "map_size",
            "max_steps",
            "workload_mode",
            "task_revision",
            "model_version",
        ):
            self.assertNotRegex(request, rf"\b{forbidden}\s*=")
        for required in (
            "client",
            "environment_instance_id",
            "supported_session_protocol_versions",
            "supported_observation_schemas",
            "supported_action_schemas",
            "idempotency_key",
        ):
            self.assertRegex(request, rf"\b{required}\s*=")
        self.assertRegex(response, r"\bstring\s+session_id\s*=")
        self.assertRegex(response, r"\buint64\s+lifecycle_epoch\s*=")
        self.assertRegex(response, r"\bMazeTaskSpec\s+task_spec\s*=")

    def test_server_assigns_episode_and_evaluation_identity(self):
        request = block(self.task_code, "message", "BeginEpisodeReq")
        response = block(self.task_code, "message", "BeginEpisodeRsp")
        assignment = block(self.task_code, "message", "EpisodeAssignment")
        evaluation = block(self.task_code, "message", "EvaluationAssignment")
        self.assertNotRegex(request, r"\b(?:string|uint64|int64)\s+episode_id\s*=")
        self.assertRegex(response, r"\bEpisodeAssignment\s+assignment\s*=")
        self.assertRegex(assignment, r"\bstring\s+episode_id\s*=")
        self.assertRegex(assignment, r"\bEvaluationAssignment\s+evaluation\s*=")
        self.assertRegex(evaluation, r"\bstring\s+evaluation_id\s*=")
        self.assertRegex(
            evaluation,
            r"\bbool\s+training_sample_emission_allowed\s*=",
        )

    def test_every_mutating_task_rpc_uses_lifecycle_command(self):
        command = block(self.task_code, "message", "LifecycleCommand")
        for field in (
            "task",
            "session_id",
            "episode_id",
            "evaluation_id",
            "lifecycle_epoch",
            "command_sequence",
            "idempotency_key",
            "expected_task_state",
            "expected_session_state",
            "expected_episode_state",
            "expected_evaluation_state",
        ):
            self.assertRegex(command, rf"\b{field}\s*=")
        for request_name in (
            "InitReq",
            "BeginEpisodeReq",
            "UpdateReq",
            "EndEpisodeReq",
            "AbortEpisodeReq",
            "CloseSessionReq",
        ):
            with self.subTest(request=request_name):
                request = block(self.task_code, "message", request_name)
                self.assertRegex(request, r"\bLifecycleCommand\s+command\s*=")

    def test_lifecycle_errors_are_classifiable_and_fail_closed(self):
        errors = block(self.task_code, "enum", "LifecycleErrorCode")
        for name in (
            "INVALID_IDENTITY",
            "INVALID_DIGEST",
            "UNSUPPORTED_SCHEMA",
            "STALE_EPOCH",
            "OUT_OF_ORDER",
            "IDEMPOTENCY_CONFLICT",
            "STATE_CONFLICT",
            "TASK_REVISION_MISMATCH",
            "MAP_INVALID",
            "MODEL_IDENTITY_MISMATCH",
        ):
            self.assertRegex(errors, rf"\bLIFECYCLE_ERROR_CODE_{name}\s*=")

    def test_map_descriptor_has_canonical_v4_inputs(self):
        descriptor = block(self.task_code, "message", "MapDescriptor")
        for field in (
            "map_id",
            "format_version",
            "grid_columns",
            "grid_rows",
            "grid_size_microunits",
            "start_grid_x",
            "start_grid_y",
            "goal_grid_x",
            "goal_grid_y",
            "blocked_bitmap",
            "canonical_digest",
            "shortest_action_steps",
            "action_rule_id",
        ):
            self.assertRegex(descriptor, rf"\b{field}\s*=")

    def test_client_reports_environment_state_not_observation(self):
        agent = block(self.task_code, "message", "AgentState")
        self.assertNotRegex(agent, r"\b(?:repeated\s+)?float\s+obs(?:ervation)?\s*=")
        self.assertRegex(agent, r"\bVec2\s+position\s*=")
        self.assertRegex(agent, r"\bbool\s+last_move_blocked\s*=")

    def test_sample_is_task_neutral_and_complete(self):
        sample = block(self.training_code, "message", "Sample")
        for field in (
            "observation",
            "next_observation",
            "action",
            "reward",
            "old_log_probability",
            "old_value_prediction",
            "terminated",
            "truncated",
            "end_kind",
            "action_step",
        ):
            self.assertRegex(sample, rf"\b{field}\s*=")
        self.assertNotRegex(sample, r"\breward_details\s*=")
        self.assertNotRegex(sample, r"\btermination_reason\s*=")

    def test_sample_batch_binds_payload_policy_semantics_and_producer(self):
        batch = block(self.training_code, "message", "SampleBatch")
        for typed_field in (
            r"ContentDigest\s+payload_digest",
            r"BehaviorPolicyIdentity\s+behavior_policy",
            r"TrainingSemanticsIdentity\s+training_semantics",
            r"ServiceInstanceIdentity\s+producer",
            r"ContractIdentity\s+contract",
        ):
            self.assertRegex(batch, rf"\b{typed_field}\s*=")
        for forbidden in ("map_id", "task_id", "curriculum_stage"):
            self.assertNotRegex(batch, rf"\b{forbidden}\s*=")

    def test_model_and_training_identities_are_layered(self):
        model = block(self.training_code, "message", "ModelIdentity")
        for field in (
            "model_lineage_id",
            "model_version",
            "artifact_digest",
            "manifest_digest",
        ):
            self.assertRegex(model, rf"\b{field}\s*=")
        semantics = block(self.training_code, "message", "TrainingSemanticsIdentity")
        for field in (
            "training_contract_id",
            "observation_schema",
            "action_schema",
            "reward_schema",
            "policy_distribution_schema_id",
            "model_architecture_id",
            "semantics_digest",
        ):
            self.assertRegex(semantics, rf"\b{field}\s*=")

    def test_model_manifest_has_schema_shape_config_and_lineage(self):
        manifest = block(self.training_code, "message", "ModelArtifactManifest")
        for field in (
            "contract",
            "identity",
            "observation_schema",
            "action_schema",
            "model_architecture_id",
            "tensor_dtype",
            "input_shape",
            "action_shape",
            "value_shape",
            "train_updates",
            "trained_samples",
            "training_config_digest",
            "training_semantics",
        ):
            self.assertRegex(manifest, rf"\b{field}\s*=")
        self.assertNotRegex(manifest, r"\bmap_id\s*=")
        self.assertNotRegex(manifest, r"\bcurriculum_stage\s*=")

    def test_metric_registry_preserves_aggregation_inputs(self):
        descriptor = block(self.training_code, "message", "MetricDescriptor")
        for field in (
            "field_id",
            "label",
            "group",
            "dimension",
            "unit",
            "scope",
            "statistic",
            "value_kind",
            "owner_component",
            "aggregation_kind",
            "window_kind",
            "schema_identity",
        ):
            self.assertRegex(descriptor, rf"\b{field}\s*=")
        value = block(self.training_code, "message", "MetricValue")
        self.assertRegex(value, r"\bdouble\s+sum\s*=")
        self.assertRegex(value, r"\buint64\s+count\s*=")
        self.assertRegex(value, r"\bdouble\s+quantile\s*=")

    def test_generator_and_manifest_bind_all_three_contracts(self):
        generator = (REPOSITORY / "scripts" / "generate.sh").read_text(
            encoding="utf-8"
        )
        builder = (REPOSITORY / "build_artifact.sh").read_text(encoding="utf-8")
        for filename in ("common.proto", "training.proto", "maze_task.proto"):
            self.assertIn(filename, generator)
            self.assertIn(filename, builder)
        for field in (
            "source_digest",
            "artifact_digest",
            "platform",
            "generator_identity",
            "contract_packages",
        ):
            self.assertIn(field, builder)


if __name__ == "__main__":
    unittest.main()
