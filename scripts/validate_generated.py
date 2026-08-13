#!/usr/bin/env python3
"""Executable wire checks for generated metric-event bindings."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from python import common_pb2, training_pb2


SCHEMA_DIRECTORY = Path(os.environ.get("RL_METRIC_SCHEMA_DIR", "/output/schemas"))
CATALOG_PATH = SCHEMA_DIRECTORY / "maze.metrics.v2.json"
CATALOG_DIGEST_PATH = SCHEMA_DIRECTORY / "maze.metrics.v2.sha256"


def load_metric_catalog() -> tuple[dict, str]:
    catalog_bytes = CATALOG_PATH.read_bytes()
    catalog = json.loads(catalog_bytes)
    digest = hashlib.sha256(catalog_bytes).hexdigest()
    assert CATALOG_DIGEST_PATH.read_text(encoding="utf-8").strip() == digest
    assert catalog["schema_id"] == "maze.metrics.v2"
    assert catalog["schema_version"] == 2
    fields = catalog["fields"]
    identities = [(field["fact"], field["field_id"]) for field in fields]
    assert identities == sorted(identities)
    assert len(identities) == len(set(identities))
    assert all(field["aggregation"] == "raw_sum_count" for field in fields)
    return catalog, digest


def sha256(value: str) -> common_pb2.ContentDigest:
    return common_pb2.ContentDigest(
        algorithm=common_pb2.DIGEST_ALGORITHM_SHA256,
        hex=value * 64,
    )


def deterministic_digest(batch: training_pb2.MetricBatch) -> str:
    canonical = training_pb2.MetricBatch()
    canonical.CopyFrom(batch)
    canonical.ClearField("batch_digest")
    return hashlib.sha256(
        canonical.SerializeToString(deterministic=True)
    ).hexdigest()


def validate_batch(
    batch: training_pb2.MetricBatch,
    catalog_fields: dict[str, set[str]],
) -> None:
    assert batch.batch_sequence > 0
    assert batch.schema_identity.schema_id == "maze.metrics.v2"
    assert batch.schema_identity.schema_version == 2
    assert batch.batch_digest.algorithm == common_pb2.DIGEST_ALGORITHM_SHA256
    assert deterministic_digest(batch) == batch.batch_digest.hex
    if batch.events:
        assert not batch.heartbeat
        assert not batch.HasField("gap")
        sequences = [event.event_sequence for event in batch.events]
        assert sequences[0] > 0
        assert sequences == sorted(set(sequences))
        assert batch.first_event_sequence == sequences[0]
        assert batch.last_event_sequence == sequences[-1]
        for event in batch.events:
            assert event.contract == batch.contract
            assert event.schema_identity == batch.schema_identity
            assert event.source == batch.source
            fact = event.WhichOneof("fact")
            assert fact in {"episode", "train_update"}
            if fact == "episode":
                assert event.episode.agents
                agent_ids = [agent.agent_id for agent in event.episode.agents]
                assert len(agent_ids) == len(set(agent_ids))
                for agent in event.episode.agents:
                    assert agent.behavior_model_lineage_id
                    assert (
                        agent.behavior_model_version_min
                        <= agent.behavior_model_version_max
                    )
                    component_ids = [
                        component.field_id
                        for component in agent.reward_components
                    ]
                    assert len(component_ids) == len(set(component_ids))
                    for component in agent.reward_components:
                        assert component.field_id and component.count > 0
                        assert component.field_id in catalog_fields["agent_episode"]
            else:
                update = event.train_update
                assert update.behavior_model_lineage_id
                assert (
                    update.behavior_model_version_min
                    <= update.behavior_model_version_max
                )
                statistic_ids = [
                    statistic.field_id for statistic in update.ppo_statistics
                ]
                assert len(statistic_ids) == len(set(statistic_ids))
                for statistic in update.ppo_statistics:
                    assert statistic.field_id and statistic.count > 0
                    assert statistic.field_id in catalog_fields["train_update"]
    elif batch.HasField("gap"):
        assert not batch.heartbeat
        assert (
            0 < batch.gap.first_unavailable_event_sequence
            <= batch.gap.last_unavailable_event_sequence
            < batch.gap.oldest_available_event_sequence
        )
        assert (
            batch.first_event_sequence
            == batch.gap.first_unavailable_event_sequence
        )
        assert (
            batch.last_event_sequence
            == batch.gap.last_unavailable_event_sequence
        )
    else:
        assert batch.heartbeat
        assert batch.first_event_sequence == 0
        assert batch.last_event_sequence == 0
    if batch.source_final:
        if batch.events or batch.HasField("gap"):
            assert batch.final_event_sequence > 0
            assert batch.final_event_sequence == batch.last_event_sequence
        else:
            assert batch.heartbeat


@dataclass
class ReferenceMetricJournal:
    batches: list[training_pb2.MetricBatch]
    catalog_fields: dict[str, set[str]]
    committed: training_pb2.MetricBatchCursor = field(
        default_factory=training_pb2.MetricBatchCursor
    )

    def __post_init__(self) -> None:
        assert self.batches
        assert self.batches[-1].source_final
        assert not any(batch.source_final for batch in self.batches[:-1])
        last_observed_event_sequence = 0
        for batch in self.batches:
            validate_batch(batch, self.catalog_fields)
            if batch.events or batch.HasField("gap"):
                last_observed_event_sequence = batch.last_event_sequence
        assert (
            self.batches[-1].final_event_sequence
            == last_observed_event_sequence
        )
        watermarks = [batch.event_time_watermark_unix_ms for batch in self.batches]
        assert watermarks == sorted(watermarks)
        self.committed.source.CopyFrom(self.batches[0].source)

    def _next_index(self) -> int:
        if self.committed.acknowledged_batch_sequence == 0:
            return 0
        for index, batch in enumerate(self.batches):
            if (
                batch.batch_sequence
                == self.committed.acknowledged_batch_sequence
            ):
                return index + 1
        return -1

    def get(
        self, cursor: training_pb2.MetricBatchCursor
    ) -> tuple[int, training_pb2.MetricBatch | None]:
        if cursor != self.committed:
            return training_pb2.METRIC_BATCH_RESULT_REJECTED_CURSOR, None
        index = self._next_index()
        assert index >= 0
        if index == len(self.batches):
            assert self.batches and self.batches[-1].source_final
            return training_pb2.METRIC_BATCH_RESULT_FINAL, None
        batch = self.batches[index]
        validate_batch(batch, self.catalog_fields)
        return training_pb2.METRIC_BATCH_RESULT_DELIVERED, batch

    def ack(self, cursor: training_pb2.MetricBatchCursor) -> int:
        if cursor == self.committed:
            return training_pb2.METRIC_BATCH_ACK_RESULT_ALREADY_APPLIED
        index = self._next_index()
        if index >= len(self.batches):
            return training_pb2.METRIC_BATCH_ACK_RESULT_REJECTED_CURSOR
        expected = self.batches[index]
        if (
            cursor.source != expected.source
            or cursor.acknowledged_batch_sequence != expected.batch_sequence
            or cursor.acknowledged_batch_digest != expected.batch_digest
        ):
            return training_pb2.METRIC_BATCH_ACK_RESULT_REJECTED_CURSOR
        if expected.events:
            expected_event = expected.last_event_sequence
        elif expected.HasField("gap"):
            expected_event = expected.gap.last_unavailable_event_sequence
        else:
            expected_event = self.committed.acknowledged_event_sequence
        if cursor.acknowledged_event_sequence != expected_event:
            return training_pb2.METRIC_BATCH_ACK_RESULT_REJECTED_CURSOR
        self.committed.CopyFrom(cursor)
        return training_pb2.METRIC_BATCH_ACK_RESULT_APPLIED


def main() -> None:
    catalog, catalog_digest = load_metric_catalog()
    catalog_fields = {
        fact: {
            field["field_id"]
            for field in catalog["fields"]
            if field["fact"] == fact
        }
        for fact in ("agent_episode", "train_update")
    }
    contract = common_pb2.ContractIdentity(
        package_name="rl-contracts",
        package_version="0.11.0",
        source_digest=sha256("1"),
        artifact_digest=sha256("2"),
        platform="linux/arm64",
        generator_identity="metric-event-wire-check",
    )
    schema = common_pb2.SchemaIdentity(
        schema_id="maze.metrics.v2",
        schema_version=2,
        canonical_digest=common_pb2.ContentDigest(
            algorithm=common_pb2.DIGEST_ALGORITHM_SHA256,
            hex=catalog_digest,
        ),
    )
    source = common_pb2.ServiceInstanceIdentity(
        component="rl-aiserver",
        instance_id="aiserver-0",
        lifecycle_epoch=7,
    )
    event = training_pb2.MetricEvent(
        contract=contract,
        schema_identity=schema,
        source=source,
        event_sequence=11,
        committed_at_unix_ms=1_786_500_000_000,
        episode=training_pb2.EpisodeMetricFact(
            task_id="maze.fixed.single-map.v1",
            environment_instance_id="env-0",
            episode_id="episode-11",
            agents=[
                training_pb2.AgentEpisodeMetricFact(
                    agent_id=1,
                    episode_return=8.5,
                    transition_count=120,
                    success=True,
                    termination_reason="GOAL_REACHED",
                    reward_components=[
                        training_pb2.RawMetricSumCount(
                            field_id="goal_reward", sum=10.0, count=120
                        ),
                        training_pb2.RawMetricSumCount(
                            field_id="wasted_action_penalty",
                            sum=-1.5,
                            count=120,
                        ),
                    ],
                    behavior_model_version_min=98,
                    behavior_model_version_max=101,
                    behavior_model_lineage_id="local-training",
                ),
                training_pb2.AgentEpisodeMetricFact(
                    agent_id=2,
                    episode_return=-2.0,
                    transition_count=1_504,
                    success=False,
                    termination_reason="TIME_LIMIT",
                    reward_components=[
                        training_pb2.RawMetricSumCount(
                            field_id="timeout_penalty",
                            sum=-2.0,
                            count=1_504,
                        )
                    ],
                    behavior_model_version_min=98,
                    behavior_model_version_max=101,
                    behavior_model_lineage_id="local-training",
                ),
            ],
        ),
    )
    batch = training_pb2.MetricBatch(
        contract=contract,
        schema_identity=schema,
        source=source,
        batch_sequence=4,
        created_at_unix_ms=1_786_500_005_000,
        first_event_sequence=11,
        last_event_sequence=11,
        events=[event],
        event_time_watermark_unix_ms=1_786_500_000_000,
    )
    digest = deterministic_digest(batch)
    assert digest == (
        "93d04f256a124eb2b7b9ae13182a07cfe7287b5efd28211bc0b2c4dc22cc2c41"
    )
    batch.batch_digest.CopyFrom(
        common_pb2.ContentDigest(
            algorithm=common_pb2.DIGEST_ALGORITHM_SHA256,
            hex=digest,
        )
    )

    wire = batch.SerializeToString(deterministic=True)
    replay = training_pb2.MetricBatch.FromString(wire)
    validate_batch(replay, catalog_fields)
    assert replay.SerializeToString(deterministic=True) == wire
    assert deterministic_digest(replay) == digest
    assert replay.first_event_sequence == replay.last_event_sequence == 11
    assert len(replay.events[0].episode.agents) == 2
    assert sum(agent.success for agent in replay.events[0].episode.agents) == 1
    assert sum(
        component.sum
        for agent in replay.events[0].episode.agents
        for component in agent.reward_components
    ) == 6.5

    cursor = training_pb2.MetricBatchCursor(
        source=source,
        acknowledged_batch_sequence=replay.batch_sequence,
        acknowledged_event_sequence=replay.last_event_sequence,
        acknowledged_batch_digest=replay.batch_digest,
    )
    assert cursor.acknowledged_batch_digest.hex == digest

    heartbeat = training_pb2.MetricBatch(
        contract=contract,
        schema_identity=schema,
        source=source,
        batch_sequence=5,
        created_at_unix_ms=1_786_500_010_000,
        heartbeat=True,
        source_final=True,
        final_event_sequence=11,
        event_time_watermark_unix_ms=1_786_500_000_000,
    )
    heartbeat.batch_digest.CopyFrom(
        common_pb2.ContentDigest(
            algorithm=common_pb2.DIGEST_ALGORITHM_SHA256,
            hex=deterministic_digest(heartbeat),
        )
    )
    assert heartbeat.batch_digest.hex == (
        "e2658924ee995d1768f58f8bd61de41f90c9c07314d741653715ce57eaef2818"
    )
    validate_batch(heartbeat, catalog_fields)

    gap = training_pb2.MetricBatch(
        contract=contract,
        schema_identity=schema,
        source=source,
        batch_sequence=6,
        created_at_unix_ms=1_786_500_015_000,
        first_event_sequence=12,
        last_event_sequence=14,
        gap=training_pb2.MetricSequenceGap(
            first_unavailable_event_sequence=12,
            last_unavailable_event_sequence=14,
            oldest_available_event_sequence=15,
            reason="bounded journal eviction",
        ),
    )
    gap.batch_digest.CopyFrom(
        common_pb2.ContentDigest(
            algorithm=common_pb2.DIGEST_ALGORITHM_SHA256,
            hex=deterministic_digest(gap),
        )
    )
    assert gap.batch_digest.hex == (
        "f44dd7ce4010dcdac5335c4c46991c1f08a4d316c64aaa9606fd60b4514c8bf2"
    )
    validate_batch(gap, catalog_fields)

    ack = training_pb2.AckMetricBatchRsp(
        result=training_pb2.METRIC_BATCH_ACK_RESULT_APPLIED,
        producer=source,
        committed_cursor=cursor,
    )
    assert ack.committed_cursor == cursor

    model_range = training_pb2.GetModelManifestRsp(
        ret_code=0,
        available_floor_model_version=0,
        latest_available_model_version=0,
    )
    model_range_roundtrip = training_pb2.GetModelManifestRsp.FromString(
        model_range.SerializeToString(deterministic=True)
    )
    assert model_range_roundtrip.HasField("available_floor_model_version")
    assert model_range_roundtrip.HasField("latest_available_model_version")
    assert model_range_roundtrip.available_floor_model_version == 0
    assert model_range_roundtrip.latest_available_model_version == 0

    update_event = training_pb2.MetricEvent(
        contract=contract,
        schema_identity=schema,
        source=common_pb2.ServiceInstanceIdentity(
            component="rl-learner",
            instance_id="learner-0",
            lifecycle_epoch=3,
        ),
        event_sequence=1,
        committed_at_unix_ms=1_786_500_020_000,
        train_update=training_pb2.TrainUpdateMetricFact(
            train_update_id="train-update-00000101",
            train_update_sequence=101,
            published_model=training_pb2.ModelIdentity(
                model_lineage_id="local-training",
                model_version=101,
                artifact_digest=sha256("4"),
                manifest_digest=sha256("5"),
            ),
            delivery_id="delivery-101",
            cumulative_trained_samples=55_296,
            actual_batch_size=512,
            behavior_model_version_min=98,
            behavior_model_version_max=100,
            behavior_model_lineage_id="local-training",
            ppo_statistics=[
                training_pb2.RawMetricSumCount(
                    field_id="policy_loss", sum=-3.25, count=4
                )
            ],
        ),
    )
    update_batch = training_pb2.MetricBatch(
        contract=contract,
        schema_identity=schema,
        source=update_event.source,
        batch_sequence=1,
        created_at_unix_ms=1_786_500_025_000,
        first_event_sequence=1,
        last_event_sequence=1,
        events=[update_event],
        event_time_watermark_unix_ms=1_786_500_020_000,
    )
    update_batch.batch_digest.CopyFrom(
        common_pb2.ContentDigest(
            algorithm=common_pb2.DIGEST_ALGORITHM_SHA256,
            hex=deterministic_digest(update_batch),
        )
    )
    assert update_batch.batch_digest.hex == (
        "db9b78def0a505bee7f307053fbd8e8fdaa33879513632b0a829f6c157e4c590"
    )
    validate_batch(update_batch, catalog_fields)
    assert update_batch.events[0].WhichOneof("fact") == "train_update"

    initial_cursor = training_pb2.MetricBatchCursor(source=source)
    journal = ReferenceMetricJournal([replay, heartbeat], catalog_fields)
    result, first = journal.get(initial_cursor)
    assert result == training_pb2.METRIC_BATCH_RESULT_DELIVERED
    assert first is not None and first.batch_digest == replay.batch_digest
    retry_result, retry = journal.get(initial_cursor)
    assert retry_result == result and retry == first
    wrong = training_pb2.MetricBatchCursor(
        source=source,
        acknowledged_batch_sequence=replay.batch_sequence,
        acknowledged_event_sequence=replay.last_event_sequence,
        acknowledged_batch_digest=sha256("f"),
    )
    assert (
        journal.ack(wrong)
        == training_pb2.METRIC_BATCH_ACK_RESULT_REJECTED_CURSOR
    )
    assert journal.committed == initial_cursor
    assert journal.ack(cursor) == training_pb2.METRIC_BATCH_ACK_RESULT_APPLIED
    assert (
        journal.ack(cursor)
        == training_pb2.METRIC_BATCH_ACK_RESULT_ALREADY_APPLIED
    )
    result, final_batch = journal.get(cursor)
    assert result == training_pb2.METRIC_BATCH_RESULT_DELIVERED
    assert final_batch is not None and final_batch.source_final
    final_cursor = training_pb2.MetricBatchCursor(
        source=source,
        acknowledged_batch_sequence=heartbeat.batch_sequence,
        acknowledged_event_sequence=cursor.acknowledged_event_sequence,
        acknowledged_batch_digest=heartbeat.batch_digest,
    )
    assert (
        journal.ack(final_cursor)
        == training_pb2.METRIC_BATCH_ACK_RESULT_APPLIED
    )
    result, no_batch = journal.get(final_cursor)
    assert result == training_pb2.METRIC_BATCH_RESULT_FINAL
    assert no_batch is None

    empty_source = common_pb2.ServiceInstanceIdentity(
        component="rl-aiserver",
        instance_id="aiserver-empty",
        lifecycle_epoch=8,
    )
    empty_final = training_pb2.MetricBatch(
        contract=contract,
        schema_identity=schema,
        source=empty_source,
        batch_sequence=1,
        created_at_unix_ms=1_786_500_030_000,
        heartbeat=True,
        source_final=True,
        final_event_sequence=0,
        event_time_watermark_unix_ms=1_786_500_030_000,
    )
    empty_final.batch_digest.CopyFrom(
        common_pb2.ContentDigest(
            algorithm=common_pb2.DIGEST_ALGORITHM_SHA256,
            hex=deterministic_digest(empty_final),
        )
    )
    assert empty_final.batch_digest.hex == (
        "102861b8e277b248f4355cbb093f6064d337c7ab3e3d385bd52079603f515d87"
    )
    validate_batch(empty_final, catalog_fields)
    empty_initial_cursor = training_pb2.MetricBatchCursor(
        source=empty_source
    )
    empty_journal = ReferenceMetricJournal(
        [empty_final], catalog_fields
    )
    result, delivered_empty_final = empty_journal.get(empty_initial_cursor)
    assert result == training_pb2.METRIC_BATCH_RESULT_DELIVERED
    assert delivered_empty_final == empty_final
    empty_final_cursor = training_pb2.MetricBatchCursor(
        source=empty_source,
        acknowledged_batch_sequence=1,
        acknowledged_event_sequence=0,
        acknowledged_batch_digest=empty_final.batch_digest,
    )
    assert (
        empty_journal.ack(empty_final_cursor)
        == training_pb2.METRIC_BATCH_ACK_RESULT_APPLIED
    )
    result, no_batch = empty_journal.get(empty_final_cursor)
    assert result == training_pb2.METRIC_BATCH_RESULT_FINAL
    assert no_batch is None


if __name__ == "__main__":
    main()
