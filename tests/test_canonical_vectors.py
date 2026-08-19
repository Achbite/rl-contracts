import hashlib
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
EXPECTED_HEX = (
    "726c2e7461736b2e6d617a652e6d61702e763400000000040000000400000003"
    "000f424000000000000000000000000300000002000000021200000000226d61"
    "7a652e616374696f6e2e392d7761792e6e6f2d636f726e65722d6375742e7631"
)
EXPECTED_SHA256 = "eb85be8438a832b83286fefa65aef51a168925e7f424a1120a01ecd9596a3fc6"


def append_u32(output: bytearray, value: int) -> None:
    output.extend(struct.pack(">I", value))


def append_i32(output: bytearray, value: int) -> None:
    output.extend(struct.pack(">i", value))


def canonical_map_bytes(*, goal_x: int = 3) -> bytes:
    output = bytearray(b"rl.task.maze.map.v4\0")
    for value in (4, 4, 3, 1_000_000):
        append_u32(output, value)
    for value in (0, 0, goal_x, 2):
        append_i32(output, value)
    bitmap = bytes.fromhex("1200")
    append_u32(output, len(bitmap))
    output.extend(bitmap)
    action_rule = b"maze.action.9-way.no-corner-cut.v1"
    append_u32(output, len(action_rule))
    output.extend(action_rule)
    return bytes(output)


class CanonicalVectorTest(unittest.TestCase):
    def test_python_vector_is_locked(self):
        canonical = canonical_map_bytes()
        self.assertEqual(canonical.hex(), EXPECTED_HEX)
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), EXPECTED_SHA256)

    def test_cpp_and_python_vectors_match(self):
        compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
        if compiler is None:
            self.fail("a C++17 compiler is required for the cross-language golden vector")
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "canonical-map-vector"
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    str(REPOSITORY / "tests" / "canonical_map_vector.cpp"),
                    "-o",
                    str(binary),
                ],
                check=True,
            )
            cpp_hex = subprocess.check_output([str(binary)], text=True).strip()
        self.assertEqual(cpp_hex, EXPECTED_HEX)
        self.assertEqual(
            hashlib.sha256(bytes.fromhex(cpp_hex)).hexdigest(), EXPECTED_SHA256
        )

    def test_tampered_field_changes_digest(self):
        canonical = canonical_map_bytes()
        tampered = canonical_map_bytes(goal_x=2)
        self.assertNotEqual(canonical, tampered)
        self.assertNotEqual(
            hashlib.sha256(canonical).digest(), hashlib.sha256(tampered).digest()
        )
