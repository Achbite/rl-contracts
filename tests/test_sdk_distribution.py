import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest


class SdkDistributionTest(unittest.TestCase):
    def test_exported_sdk_builds_two_independent_consumers(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="rl-sdk-consumers-") as temporary:
            root = Path(temporary)
            subprocess.run(["bash", str(repository / "sdk/build_artifact.sh"), str(root)], check=True, timeout=30)
            with tarfile.open(root / "RL-SDK.tar.gz") as package:
                package.extractall(root, filter="data")
            # Exercise the whole CMake -> generator -> protoc plugin path with
            # an explicit interpreter, while PATH's default Python cannot run.
            alternate = root / "alternate-path"
            alternate.mkdir()
            wrong_python = alternate / "python3"
            wrong_python.write_text("#!/bin/sh\nexit 83\n")
            wrong_python.chmod(0o755)
            build_environment = {**os.environ, "PATH": str(alternate) + os.pathsep + os.environ["PATH"]}
            projects = {}
            for role in ("server", "client"):
                source = root / role
                shutil.copytree(repository / "tests/fixtures/sdk_task", source)
                build = root / (role + "-build")
                subprocess.run(["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
                    f"-DRL_SDK_DIR={root / 'RL-SDK'}", f"-DCONSUMER_ROLE={role}",
                    f"-DPython3_EXECUTABLE={sys.executable}"], env=build_environment, check=True, timeout=120)
                projects[role] = (source, build)

            for extra_field in (False, True):
                for source, build in projects.values():
                    if extra_field:
                        proto = source / "proto/example/state.proto"
                        proto.write_text(proto.read_text().replace("/* added field */", "int32 revision = 3;"))
                        # Use the new field in both consumers without explicitly re-running configure.
                        # Missing import dependencies then fail generation/compilation or the round trip.
                        for cpp in source.glob("*.cpp"):
                            cpp.write_text(cpp.read_text().replace("#ifdef WITH_EXTRA_FIELD", "#if 1"))
                    subprocess.run(["cmake", "--build", str(build), "--parallel", "2"],
                        env=build_environment, check=True, timeout=180)
                endpoint = root / "endpoint"
                endpoint.unlink(missing_ok=True)
                server = subprocess.Popen([str(projects["server"][1] / "consumer"), str(endpoint)])
                try:
                    deadline = time.monotonic() + 5
                    while (not endpoint.exists() or endpoint.stat().st_size == 0) and server.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(endpoint.exists(), "independent server did not publish its endpoint")
                    subprocess.run([str(projects["client"][1] / "consumer"), "127.0.0.1:" + endpoint.read_text()],
                        check=True, timeout=15)
                    self.assertEqual(server.wait(timeout=10), 0)
                finally:
                    if server.poll() is None:
                        server.terminate()
                        server.wait(timeout=10)
