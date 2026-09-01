#!/usr/bin/env python3
"""Create and verify local build artifact type manifests."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any


MANIFEST_SCHEMA = "rl.artifact-manifest.v1"
TRAINING_ARTIFACT_PACKAGE = "rl-training-contracts"
TASK_MAZE_ARTIFACT_PACKAGE = "rl-task-maze-contracts"


def fail(message: str) -> None:
    raise SystemExit(message)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid artifact manifest {path}: {exc}")
    if not isinstance(document, dict):
        fail(f"artifact manifest must be an object: {path}")
    return document


def safe_relative(value: str) -> PurePosixPath:
    if not value or "\\" in value:
        fail(f"artifact path is invalid: {value!r}")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        fail(f"artifact path is invalid: {value!r}")
    return relative


def inventory(root: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.name == "manifest.json":
            continue
        if path.is_symlink():
            fail(f"artifact contains a symbolic link: {path}")
        if path.is_file():
            files.append(path.relative_to(root).as_posix())
    if not files:
        fail(f"artifact has no files: {root}")
    return files


def common_manifest(args: argparse.Namespace) -> dict[str, Any]:
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "artifact_channel": args.channel,
        "package": args.package,
        "version": args.version,
        "files": inventory(args.output.resolve()),
    }
    if getattr(args, "platform", None) is not None:
        manifest["platform"] = args.platform
    return manifest


def finalize_contract(args: argparse.Namespace) -> None:
    root = args.output.resolve()
    manifest = common_manifest(args)
    if args.package == TRAINING_ARTIFACT_PACKAGE:
        manifest.update(
            {
                "contract_packages": [
                    "rl.common.v1",
                    "rl.training.v1",
                    "rl.training.metrics.v1",
                ],
                "metric_schemas": {
                    "rl.training.metrics": {
                        "path": "schemas/training.metrics.json",
                        "digest_path": "schemas/training.metrics.sha256",
                        "schema_version": 1,
                    }
                },
            }
        )
    elif args.package == TASK_MAZE_ARTIFACT_PACKAGE:
        manifest.update(
            {
                "contract_packages": [
                    "rl.common.v1",
                    "rl.task.maze.v1",
                    "rl.task.maze.metrics.v1",
                ],
                "dependencies": [
                    {
                        "package": TRAINING_ARTIFACT_PACKAGE,
                        "version": args.version,
                    }
                ],
                "task_protocol": {
                    "protocol_id": "rl.task.maze",
                    "protocol_version": 1,
                },
                "metric_schemas": {
                    "maze.episode.metrics": {
                        "path": "schemas/maze.episode.metrics.json",
                        "digest_path": "schemas/maze.episode.metrics.sha256",
                        "schema_version": 1,
                    }
                },
                "training_contract": {
                    "path": "schemas/training-contract.json",
                    "digest_path": "schemas/training-contract.sha256",
                },
            }
        )
    else:
        fail(f"unsupported contract artifact package: {args.package}")
    write_manifest(root, manifest)


def contract_reference(path: Path) -> dict[str, str]:
    contract = load_manifest(path)
    if (
        contract.get("schema_version") != MANIFEST_SCHEMA
        or contract.get("package") != TRAINING_ARTIFACT_PACKAGE
        or not isinstance(contract.get("version"), str)
    ):
        fail(
            "component artifact requires an rl-training-contracts "
            f"manifest: {path}"
        )
    return {
        "package": TRAINING_ARTIFACT_PACKAGE,
        "version": contract["version"],
    }


def finalize_component(args: argparse.Namespace) -> None:
    root = args.output.resolve()
    manifest = common_manifest(args)
    manifest.update(
        {
            "abi": args.abi,
            "contract": contract_reference(args.contract_manifest.resolve()),
            "executables": sorted(set(args.executable)),
        }
    )
    for relative in manifest["executables"]:
        path = root / safe_relative(relative)
        if not path.is_file() or not os.access(path, os.X_OK):
            fail(f"artifact executable is missing or not executable: {path}")
    write_manifest(root, manifest)


def write_manifest(root: Path, document: dict[str, Any]) -> None:
    (root / "manifest.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    manifest_path = root / "manifest.json"
    manifest = load_manifest(manifest_path)
    expected = {
        "schema_version": MANIFEST_SCHEMA,
        "package": args.package,
        "version": args.version,
    }
    if args.platform is not None:
        expected["platform"] = args.platform
    if args.channel is not None:
        expected["artifact_channel"] = args.channel
    for key, value in expected.items():
        if manifest.get(key) != value:
            fail(
                f"artifact {key} mismatch in {manifest_path}: "
                f"expected {value!r}, found {manifest.get(key)!r}"
            )

    declared = manifest.get("files")
    if not isinstance(declared, list) or not declared:
        fail(f"artifact files list is invalid: {manifest_path}")
    for value in declared:
        if not isinstance(value, str):
            fail(f"artifact files list is invalid: {manifest_path}")
        path = root / safe_relative(value)
        if not path.is_file() or path.is_symlink():
            fail(f"artifact file is missing or invalid: {path}")

    for value in args.require_file:
        path = root / safe_relative(value)
        if not path.is_file() or path.is_symlink():
            fail(f"required artifact file is missing or invalid: {path}")
    for value in args.require_executable:
        path = root / safe_relative(value)
        if not path.is_file() or path.is_symlink() or not os.access(path, os.X_OK):
            fail(f"required artifact executable is missing or invalid: {path}")

    if args.contract_manifest is not None:
        if manifest.get("contract") != contract_reference(
            args.contract_manifest.resolve()
        ):
            fail(f"artifact contract type is incompatible: {manifest_path}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)

    contract = commands.add_parser("finalize-contract")
    contract.add_argument("--output", type=Path, required=True)
    contract.add_argument(
        "--package",
        choices=(TRAINING_ARTIFACT_PACKAGE, TASK_MAZE_ARTIFACT_PACKAGE),
        required=True,
    )
    contract.add_argument("--version", required=True)
    contract.add_argument(
        "--channel", choices=("production", "development"), required=True
    )

    component = commands.add_parser("finalize-component")
    component.add_argument("--output", type=Path, required=True)
    component.add_argument("--package", required=True)
    component.add_argument("--version", required=True)
    component.add_argument("--platform", required=True)
    component.add_argument(
        "--channel", choices=("production", "development"), required=True
    )
    component.add_argument("--contract-manifest", type=Path, required=True)
    component.add_argument("--abi", default="cxx17-grpc-debian13")
    component.add_argument("--executable", action="append", default=[])

    check = commands.add_parser("verify")
    check.add_argument("--root", type=Path, required=True)
    check.add_argument("--package", required=True)
    check.add_argument("--version", required=True)
    check.add_argument("--platform")
    check.add_argument("--channel", choices=("production", "development"))
    check.add_argument("--contract-manifest", type=Path)
    check.add_argument("--require-file", action="append", default=[])
    check.add_argument("--require-executable", action="append", default=[])
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "finalize-contract":
        finalize_contract(args)
    elif args.command == "finalize-component":
        finalize_component(args)
    elif args.command == "verify":
        verify(args)
    else:
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
