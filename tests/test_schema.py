import hashlib
import json
import re
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
COMMON_PROTO = REPOSITORY / "proto" / "v1" / "common.proto"
TRAINING_PROTO = REPOSITORY / "proto" / "v1" / "training.proto"
MAZE_TASK_PROTO = REPOSITORY / "proto" / "v1" / "maze_task.proto"
METRIC_CATALOG = REPOSITORY / "schemas" / "maze.metrics.v3.json"
METRIC_CATALOG_DIGEST = REPOSITORY / "schemas" / "maze.metrics.v3.sha256"


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
            "0.13.0",
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
            "BehaviorPolicyReference",
            "TrainingSemanticsIdentity",
            "ModelArtifactManifest",
            "SamplePoolIngressService",
            "SamplePoolConsumerService",
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
            "model_step",
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

    def test_server_assigns_episode_identity_and_fixed_task_horizon(self):
        request = block(self.task_code, "message", "BeginEpisodeReq")
        response = block(self.task_code, "message", "BeginEpisodeRsp")
        assignment = block(self.task_code, "message", "EpisodeAssignment")
        task_spec = block(self.task_code, "message", "MazeTaskSpec")
        self.assertNotRegex(request, r"\b(?:string|uint64|int64)\s+episode_id\s*=")
        self.assertRegex(response, r"\bEpisodeAssignment\s+assignment\s*=")
        self.assertRegex(assignment, r"\bstring\s+episode_id\s*=")
        self.assertRegex(task_spec, r"\buint32\s+episode_max_steps\s*=")
        self.assertNotRegex(self.task_code, r"\bEvaluationAssignment\b")
        self.assertNotRegex(self.task_code, r"\bEvaluationState\b")
        self.assertNotRegex(self.task_code, r"\bCurriculumStage\b")

    def test_every_mutating_task_rpc_uses_lifecycle_command(self):
        command = block(self.task_code, "message", "LifecycleCommand")
        for field in (
            "task",
            "session_id",
            "episode_id",
            "lifecycle_epoch",
            "command_sequence",
            "idempotency_key",
            "expected_task_state",
            "expected_session_state",
            "expected_episode_state",
        ):
            self.assertRegex(command, rf"\b{field}\s*=")
        for retired in ("evaluation_id", "expected_evaluation_state"):
            self.assertNotRegex(command, rf"\b(?:string|EvaluationState)\s+{retired}\s*=")
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
        self.assertRegex(
            agent,
            r"\boptional\s+int32\s+executed_action_id\s*=\s*6\s*;",
        )

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
            r"BehaviorPolicyReference\s+behavior_policy",
            r"TrainingSemanticsIdentity\s+training_semantics",
            r"ServiceInstanceIdentity\s+producer",
            r"ContractIdentity\s+contract",
        ):
            self.assertRegex(batch, rf"\b{typed_field}\s*=")
        for forbidden in ("map_id", "task_id", "curriculum_stage"):
            self.assertNotRegex(batch, rf"\b{forbidden}\s*=")

    def test_platform_control_ids_are_not_contract_fields(self):
        sources = (self.common_code, self.training_code, self.task_code)
        for source in sources:
            for field in ("task_id", "run_id", "pod_attempt_id"):
                self.assertNotRegex(
                    source,
                    rf"\b(?:optional\s+)?[A-Za-z0-9_.<>]+\s+{field}\s*=",
                )
        task_identity = block(self.task_code, "message", "TaskIdentity")
        episode_fact = block(self.training_code, "message", "EpisodeMetricFact")
        self.assertRegex(task_identity, r"\breserved\s+2\s*;")
        self.assertRegex(episode_fact, r"\breserved\s+1\s*;")
        for source in (task_identity, episode_fact):
            self.assertRegex(source, r'\breserved\s+"task_id"\s*;')

    def test_shared_policy_binding_uses_optional_model_step(self):
        binding = block(self.task_code, "message", "BehaviorPolicyBinding")
        self.assertRegex(binding, r"\boptional\s+uint64\s+model_step\s*=\s*2\s*;")
        self.assertRegex(binding, r'\breserved\s+"model_version"\s*;')

    def test_legacy_model_version_fields_are_not_declared(self):
        legacy_names = (
            "model_version",
            "reference_model_version",
            "max_version_lag",
            "minimum_behavior_model_version",
            "maximum_behavior_model_version",
            "minimum_ready_model_version",
            "maximum_ready_model_version",
            "behavior_model_version_min",
            "behavior_model_version_max",
            "available_floor_model_version",
            "latest_available_model_version",
            "behavior_versions",
        )
        for source in (self.task_code, self.training_code):
            for field in legacy_names:
                self.assertNotRegex(
                    source,
                    rf"\b(?:optional\s+|repeated\s+)?[A-Za-z0-9_.<>]+\s+{field}\s*=",
                )
        self.assertNotRegex(self.training_code, r"\bBehaviorVersionQueueStatus\b")

    def test_model_and_training_identities_are_layered(self):
        model = block(self.training_code, "message", "ModelIdentity")
        for field in (
            "model_lineage_id",
            "model_step",
            "artifact_digest",
            "manifest_digest",
        ):
            self.assertRegex(model, rf"\b{field}\s*=")
        self.assertRegex(model, r"\boptional\s+uint64\s+model_step\s*=\s*2\s*;")
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

        behavior = block(
            self.training_code, "message", "BehaviorPolicyReference"
        )
        for field in (
            "model_lineage_id",
            "model_step",
            "distribution_schema_id",
            "policy_spec_digest",
        ):
            self.assertRegex(behavior, rf"\b{field}\s*=")
        self.assertRegex(behavior, r"\boptional\s+uint64\s+model_step\s*=\s*2\s*;")
        self.assertNotRegex(behavior, r"\bartifact_digest\s*=")
        self.assertNotRegex(behavior, r"\bmanifest_digest\s*=")

    def test_get_batch_uses_single_step_bounded_freshness(self):
        request = block(self.training_code, "message", "GetBatchReq")
        self.assertRegex(request, r"\bBatchAssemblySpec\s+assembly\s*=")
        self.assertRegex(request, r"\bSampleFreshnessPolicy\s+freshness\s*=")
        self.assertRegex(
            request,
            r"\bTrainingSemanticsIdentity\s+required_semantics\s*=",
        )
        self.assertNotRegex(request, r"\btarget_model\s*=")
        assembly = block(self.training_code, "message", "BatchAssemblySpec")
        for field in ("target_samples", "max_samples", "mode"):
            self.assertRegex(assembly, rf"\b{field}\s*=")
        freshness = block(
            self.training_code, "message", "SampleFreshnessPolicy"
        )
        for field in (
            "model_lineage_id",
            "reference_model_step",
            "max_model_step_lag",
            "max_sample_age_ms",
            "distribution_schema_id",
            "policy_spec_digest",
        ):
            self.assertRegex(freshness, rf"\b{field}\s*=")

    def test_sample_pool_ingress_and_consumer_services_are_disjoint(self):
        push = block(self.training_code, "message", "PushSamplesReq")
        self.assertRegex(push, r"\breserved\s+1\s*;")
        self.assertRegex(push, r'\breserved\s+"credit_id"\s*;')
        self.assertRegex(push, r"\bSampleBatch\s+batch\s*=\s*2\s*;")

        ingress = block(
            self.training_code, "service", "SamplePoolIngressService"
        )
        consumer = block(
            self.training_code, "service", "SamplePoolConsumerService"
        )
        self.assertEqual(
            re.findall(r"\brpc\s+([A-Za-z0-9_]+)\s*\(", ingress),
            ["PushSamples", "GetStatus"],
        )
        self.assertEqual(
            re.findall(r"\brpc\s+([A-Za-z0-9_]+)\s*\(", consumer),
            [
                "GetBatch",
                "AckBatch",
                "NackBatch",
                "RenewLease",
                "FinalizeSamplePool",
                "GetStatus",
            ],
        )

        finalize_request = block(
            self.training_code, "message", "FinalizeSamplePoolReq"
        )
        self.assertRegex(
            finalize_request,
            r"\bServiceInstanceIdentity\s+consumer\s*=\s*1\s*;",
        )
        self.assertRegex(
            finalize_request,
            r"\bServiceInstanceIdentity\s+expected_sample_pool\s*=\s*2\s*;",
        )
        self.assertRegex(
            finalize_request, r"\bstring\s+finalization_id\s*=\s*3\s*;"
        )
        finalize_response = block(
            self.training_code, "message", "FinalizeSamplePoolRsp"
        )
        for field in (
            "result",
            "finalization_id",
            "sample_pool",
            "settled_samples",
            "settled_fragments",
            "ready_samples",
            "leased_samples",
            "resident_samples",
            "finalized_at_unix_ms",
        ):
            self.assertRegex(finalize_response, rf"\b{field}\s*=")
        finalize_result = block(
            self.training_code, "enum", "SamplePoolFinalizeResult"
        )
        for name in (
            "FINALIZED",
            "ALREADY_FINALIZED",
            "REJECTED_ACTIVE_LEASE",
            "REJECTED_IDENTITY",
            "REJECTED_CONFLICT",
        ):
            self.assertRegex(
                finalize_result,
                rf"\bSAMPLE_POOL_FINALIZE_RESULT_{name}\s*=",
            )
        push_result = block(self.training_code, "enum", "PushResult")
        self.assertRegex(
            push_result, r"\bPUSH_RESULT_REJECTED_FINALIZED\s*=\s*7\s*;"
        )

        status = block(self.training_code, "message", "SamplePoolStatusRsp")
        self.assertRegex(
            status,
            r"\bServiceInstanceIdentity\s+sample_pool\s*=\s*2\s*;",
        )
        self.assertRegex(status, r"\breserved\s+48\s+to\s+65\s*;")
        for field in ("evicted_sample_count", "evicted_fragment_count"):
            self.assertRegex(status, rf"\bint64\s+{field}\s*=")
        self.assertRegex(status, r"\bbool\s+finalized\s*=\s*68\s*;")
        self.assertRegex(
            status, r"\bstring\s+finalization_id\s*=\s*69\s*;"
        )
        for field in (
            "finalized_at_unix_ms",
            "finalized_sample_count",
            "finalized_fragment_count",
        ):
            self.assertRegex(status, rf"\bint64\s+{field}\s*=")
        for response_name, field_number in (("PushSamplesRsp", 12), ("GetBatchRsp", 13)):
            response = block(self.training_code, "message", response_name)
            self.assertRegex(
                response,
                rf"\bServiceInstanceIdentity\s+sample_pool\s*=\s*{field_number}\s*;",
            )

        aiserver_status = block(
            self.training_code, "message", "AIServerStatusRsp"
        )
        self.assertRegex(aiserver_status, r"\breserved\s+35\s+to\s+41\s*;")
        for retired in (
            "credit_request_count",
            "credit_grant_count",
            "credit_wait_count",
            "credit_reacquire_count",
            "producer_stale_count",
            "capacity_wait_ms",
            "training_capacity_wait",
        ):
            self.assertNotRegex(
                aiserver_status,
                rf"\b(?:int64|bool)\s+{retired}\s*=",
            )

    def test_retired_demand_credit_and_distributor_names_cannot_return(self):
        retired_top_level = (
            "SampleDistributorService",
            "SampleDemandResult",
            "SampleCreditResult",
            "SampleCreditState",
            "SampleCreditReleaseReason",
            "SampleDemand",
            "UpsertSampleDemandReq",
            "ReleaseSampleDemandReq",
            "GetSampleDemandStatusReq",
            "SampleDemandRsp",
            "SampleDemandStatusRsp",
            "AcquireSampleCreditReq",
            "SampleCreditGrant",
            "ReleaseSampleCreditReq",
            "ReleaseSampleCreditRsp",
            "DistributorStatusReq",
            "DistributorStatusRsp",
        )
        for name in retired_top_level:
            self.assertNotRegex(
                self.training_code,
                rf"\b(?:message|enum|service)\s+{name}\b",
            )
        for rpc in (
            "UpsertSampleDemand",
            "ReleaseSampleDemand",
            "GetSampleDemandStatus",
            "AcquireSampleCredit",
            "ReleaseSampleCredit",
        ):
            self.assertNotRegex(self.training_code, rf"\brpc\s+{rpc}\s*\(")

    def test_maze_update_has_explicit_capacity_wait(self):
        lifecycle = block(self.task_code, "enum", "LifecycleResult")
        self.assertRegex(lifecycle, r"\bLIFECYCLE_RESULT_WAIT\s*=")
        control = block(self.task_code, "enum", "EnvironmentControl")
        self.assertRegex(
            control,
            r"\bENVIRONMENT_CONTROL_WAIT_FOR_TRAINING_CAPACITY\s*=",
        )
        response = block(self.task_code, "message", "UpdateRsp")
        self.assertRegex(response, r"\bEnvironmentControl\s+environment_control\s*=")
        self.assertRegex(response, r"\bint32\s+retry_after_ms\s*=")

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
        self.assertRegex(manifest, r"\buint64\s+train_updates\s*=\s*15\s*;")
        self.assertRegex(manifest, r"\buint64\s+trained_samples\s*=\s*16\s*;")

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

    def test_metric_event_v3_preserves_raw_facts_and_replay_identity(self):
        raw = block(self.training_code, "message", "RawMetricSumCount")
        for field in ("field_id", "sum", "count"):
            self.assertRegex(raw, rf"\b{field}\s*=")

        agent = block(
            self.training_code, "message", "AgentEpisodeMetricFact"
        )
        for field in (
            "agent_id",
            "episode_return",
            "transition_count",
            "success",
            "termination_reason",
            "reward_components",
            "minimum_behavior_model_step",
            "maximum_behavior_model_step",
            "behavior_model_lineage_id",
        ):
            self.assertRegex(agent, rf"\b{field}\s*=")

        episode = block(self.training_code, "message", "EpisodeMetricFact")
        for field in (
            "environment_instance_id",
            "episode_id",
            "training_semantics",
            "agents",
        ):
            self.assertRegex(episode, rf"\b{field}\s*=")
        self.assertNotRegex(episode, r"\bstring\s+task_id\s*=")
        self.assertRegex(episode, r"\breserved\s+1\s*;")
        self.assertRegex(episode, r'\breserved\s+"task_id"\s*;')
        self.assertNotRegex(episode, r"\bmean\s*=")

        update = block(
            self.training_code, "message", "TrainUpdateMetricFact"
        )
        for field in (
            "train_update_id",
            "train_update_sequence",
            "published_model",
            "delivery_id",
            "training_semantics",
            "cumulative_trained_samples",
            "actual_batch_size",
            "minimum_behavior_model_step",
            "maximum_behavior_model_step",
            "ppo_statistics",
            "behavior_model_lineage_id",
        ):
            self.assertRegex(update, rf"\b{field}\s*=")

        event = block(self.training_code, "message", "MetricEvent")
        for field in (
            "contract",
            "schema_identity",
            "source",
            "event_sequence",
            "committed_at_unix_ms",
            "episode",
            "train_update",
        ):
            self.assertRegex(event, rf"\b{field}\s*=")

        batch = block(self.training_code, "message", "MetricBatch")
        for field in (
            "batch_sequence",
            "batch_digest",
            "first_event_sequence",
            "last_event_sequence",
            "events",
            "heartbeat",
            "source_final",
            "final_event_sequence",
            "event_time_watermark_unix_ms",
            "gap",
        ):
            self.assertRegex(batch, rf"\b{field}\s*=")
        cursor = block(self.training_code, "message", "MetricBatchCursor")
        for field in (
            "source",
            "acknowledged_batch_sequence",
            "acknowledged_event_sequence",
            "acknowledged_batch_digest",
        ):
            self.assertRegex(cursor, rf"\b{field}\s*=")
        service = block(self.training_code, "service", "MetricEventService")
        self.assertRegex(service, r"\brpc\s+GetMetricBatch\s*\(")
        self.assertRegex(service, r"\brpc\s+AckMetricBatch\s*\(")
        ack = block(self.training_code, "message", "AckMetricBatchRsp")
        self.assertRegex(ack, r"\bMetricBatchCursor\s+committed_cursor\s*=")
        self.assertIn("final_event_sequence is zero", self.training)

    def test_metric_event_v3_catalog_is_canonical_and_digest_bound(self):
        catalog_bytes = METRIC_CATALOG.read_bytes()
        digest = hashlib.sha256(catalog_bytes).hexdigest()
        self.assertEqual(
            METRIC_CATALOG_DIGEST.read_text(encoding="utf-8").strip(),
            digest,
        )
        catalog = json.loads(catalog_bytes)
        self.assertEqual(catalog["catalog_schema"], "rl.metric-field-catalog.v1")
        self.assertEqual(catalog["schema_id"], "maze.metrics.v3")
        self.assertEqual(catalog["schema_version"], 3)
        identities = [
            (field["fact"], field["field_id"])
            for field in catalog["fields"]
        ]
        self.assertEqual(identities, sorted(identities))
        self.assertEqual(len(identities), len(set(identities)))
        self.assertEqual(
            {field["aggregation"] for field in catalog["fields"]},
            {"raw_sum_count"},
        )
        policy_lag = next(
            field for field in catalog["fields"] if field["field_id"] == "policy_lag"
        )
        self.assertEqual(policy_lag["dimension"], "model_step_distance")
        self.assertEqual(policy_lag["unit"], "model_step")

    def test_model_manifest_responses_publish_contiguous_range(self):
        manifest = block(
            self.training_code, "message", "GetModelManifestRsp"
        )
        status = block(
            self.training_code, "message", "ModelDistributorStatusRsp"
        )
        for source in (manifest, status):
            self.assertRegex(
                source, r"\boptional\s+uint64\s+available_floor_model_step\s*="
            )
            self.assertRegex(
                source, r"\boptional\s+uint64\s+latest_available_model_step\s*="
            )

    def test_generator_and_manifest_bind_all_three_contracts(self):
        generator = (REPOSITORY / "scripts" / "generate.sh").read_text(
            encoding="utf-8"
        )
        builder = (REPOSITORY / "build_artifact.sh").read_text(encoding="utf-8")
        for filename in (
            "common.proto",
            "training.proto",
            "maze_task.proto",
            "maze.metrics.v3.json",
            "maze.metrics.v3.sha256",
        ):
            self.assertIn(filename, generator)
            self.assertIn(filename, builder)
        for field in (
            "source_digest",
            "artifact_digest",
            "platform",
            "generator_identity",
            "contract_packages",
            "metric_schemas",
        ):
            self.assertIn(field, builder)
