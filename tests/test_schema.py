import re
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
PROTO = REPOSITORY / "proto" / "v1" / "maze.proto"

RUN_ID_RESERVATIONS = {
    "InitReq": 6,
    "BeginEpisodeReq": 1,
    "UpdateReq": 4,
    "EpisodeEndReq": 3,
    "AbortEpisodeReq": 1,
    "SampleBatch": 6,
    "GetBatchReq": 3,
    "AckBatchReq": 1,
    "NackBatchReq": 1,
    "RenewLeaseReq": 1,
    "DistributorStatusReq": 1,
    "DistributorStatusRsp": 10,
    "AIServerStatusReq": 1,
    "AIServerStatusRsp": 2,
    "ModelArtifactManifest": 3,
    "GetModelManifestReq": 1,
    "DownloadModelReq": 1,
    "ModelChunk": 1,
    "AckModelReq": 1,
    "ModelDistributorStatusReq": 1,
    "ModelDistributorStatusRsp": 2,
}


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
        cls.source = PROTO.read_text(encoding="utf-8")

    def test_contract_version_is_breaking_release(self):
        self.assertEqual(
            (REPOSITORY / "VERSION").read_text(encoding="utf-8").strip(),
            "0.5.0",
        )

    def test_run_id_fields_are_removed_and_reserved(self):
        self.assertNotRegex(
            self.source,
            r"\b(?:string|bytes|int32|int64|uint32|uint64)\s+run_id\s*=",
        )
        for message, field_number in RUN_ID_RESERVATIONS.items():
            with self.subTest(message=message):
                body = block(self.source, "message", message)
                self.assertRegex(
                    body,
                    rf"\breserved\s+{field_number}\s*;",
                )
                self.assertRegex(body, r'\breserved\s+"run_id"\s*;')

    def test_rejected_run_enum_value_is_reserved(self):
        body = block(self.source, "enum", "PushResult")
        self.assertRegex(body, r"\breserved\s+4\s*;")
        self.assertRegex(
            body,
            r'\breserved\s+"PUSH_RESULT_REJECTED_RUN"\s*;',
        )
        self.assertNotRegex(
            body,
            r"\bPUSH_RESULT_REJECTED_RUN\s*=",
        )


if __name__ == "__main__":
    unittest.main()
