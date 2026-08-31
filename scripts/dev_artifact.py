#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"[a-f0-9]{64}")
GIT_HEAD = re.compile(r"[a-f0-9]{40}")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_metadata(repo: Path) -> dict[str, str]:
    repo = repo.resolve()
    head = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    status_output = subprocess.check_output(
        [
            "git",
            "-C",
            str(repo),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        text=True,
    )
    listed = subprocess.check_output(
        [
            "git",
            "-C",
            str(repo),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ]
    )
    relative_paths = sorted(
        raw.decode("utf-8", errors="surrogateescape")
        for raw in listed.split(b"\0")
        if raw
    )
    digest = hashlib.sha256()
    for relative in relative_paths:
        path = repo / relative
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        if not path.exists() and not path.is_symlink():
            digest.update(b"missing\0")
            continue
        mode = os.lstat(path).st_mode
        digest.update(f"{stat.S_IFMT(mode):o}:{stat.S_IMODE(mode):o}".encode("ascii"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        elif path.is_file():
            digest.update(path.read_bytes())
        else:
            raise SystemExit(f"unsupported source entry: {path}")
        digest.update(b"\0")
    return {
        "source_commit": head[:12],
        "source_digest": digest.hexdigest(),
        "source_head": head,
        "source_tree_state": "dirty" if status_output else "clean",
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid JSON document {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"JSON document must be an object: {path}")
    return value


def file_inventory(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files[str(path.relative_to(root))] = sha256_file(path)
    if not files:
        raise SystemExit(f"development artifact has no files: {root}")
    return files


def artifact_digest(files: dict[str, str]) -> dict[str, str]:
    return {
        "algorithm": "sha256",
        "hex": hashlib.sha256(canonical_json(files)).hexdigest(),
    }


def common_manifest(
    *,
    package: str,
    version: str,
    platform: str,
    source: dict[str, str],
    files: dict[str, str],
) -> dict[str, Any]:
    return {
        "artifact_channel": "development",
        "artifact_digest": artifact_digest(files),
        "development_source_digest": {
            "algorithm": "sha256",
            "hex": source["source_digest"],
        },
        "files": files,
        "package": package,
        "platform": platform,
        "source_commit": source["source_commit"],
        "source_digest": {
            "algorithm": "sha256",
            "hex": source["source_digest"],
        },
        "source_head": source["source_head"],
        "source_id": f"dev-source-{source['source_digest'][:16]}",
        "source_tree_state": source["source_tree_state"],
        "version": version,
    }


def finalize_contract(args: argparse.Namespace) -> None:
    root = args.output.resolve()
    source = source_metadata(args.repo)
    if source["source_digest"] != args.source_digest:
        raise SystemExit("contract source changed while the development artifact was built")
    files = file_inventory(root)
    generator_path = root / "generator-identity.json"
    catalog_path = root / "schemas/maze.metrics.json"
    catalog_digest_path = root / "schemas/maze.metrics.sha256"
    training_contract_path = root / "schemas/training-contract.json"
    training_contract_digest_path = root / "schemas/training-contract.sha256"
    if not generator_path.is_file():
        raise SystemExit("contract generator identity is missing")
    if not catalog_path.is_file() or not catalog_digest_path.is_file():
        raise SystemExit("contract metric schema is missing")
    if (
        not training_contract_path.is_file()
        or not training_contract_digest_path.is_file()
    ):
        raise SystemExit("training contract descriptor is missing")
    catalog_digest = sha256_file(catalog_path)
    if catalog_digest_path.read_text(encoding="utf-8").strip() != catalog_digest:
        raise SystemExit("contract metric schema digest is invalid")
    training_contract_digest = sha256_file(training_contract_path)
    if (
        training_contract_digest_path.read_text(encoding="utf-8").strip()
        != training_contract_digest
    ):
        raise SystemExit("training contract descriptor digest is invalid")
    generator_identity = hashlib.sha256(
        canonical_json(load_json(generator_path))
    ).hexdigest()
    canonical_source = hashlib.sha256()
    for path in (
        root / "common.proto",
        root / "training.proto",
        root / "maze_task.proto",
        catalog_path,
        catalog_digest_path,
        training_contract_path,
        training_contract_digest_path,
    ):
        canonical_source.update(path.name.encode("utf-8"))
        canonical_source.update(b"\0")
        canonical_source.update(path.read_bytes())
        canonical_source.update(b"\0")
    manifest = common_manifest(
        package="rl-contracts",
        version=args.version,
        platform=args.platform,
        source=source,
        files=files,
    )
    manifest["source_digest"] = {
        "algorithm": "sha256",
        "hex": canonical_source.hexdigest(),
    }
    manifest["source_id"] = f"contract-source-{canonical_source.hexdigest()[:16]}"
    manifest.update(
        {
            "contract_packages": [
                "rl.common.v1",
                "rl.training.v1",
                "rl.task.maze.v1",
            ],
            "generator_identity": generator_identity,
            "metric_schemas": {
                "maze.metrics": {
                    "canonical_digest": {
                        "algorithm": "sha256",
                        "hex": catalog_digest,
                    },
                    "digest_path": "schemas/maze.metrics.sha256",
                    "path": "schemas/maze.metrics.json",
                    "schema_version": 1,
                }
            },
            "training_contract": {
                "canonical_digest": {
                    "algorithm": "sha256",
                    "hex": training_contract_digest,
                },
                "digest_path": "schemas/training-contract.sha256",
                "path": "schemas/training-contract.json",
            },
            "schema_version": 2,
        }
    )
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def contract_binding(path: Path) -> dict[str, Any]:
    manifest = load_json(path)
    if (
        manifest.get("artifact_channel") != "development"
        or manifest.get("package") != "rl-contracts"
    ):
        raise SystemExit("component development artifact requires a development contract")
    return {
        "artifact_digest": manifest["artifact_digest"],
        "generator_identity": manifest["generator_identity"],
        "manifest_sha256": {
            "algorithm": "sha256",
            "hex": sha256_file(path),
        },
        "platform": manifest["platform"],
        "source_digest": manifest["source_digest"],
        "version": manifest["version"],
    }


def finalize_component(args: argparse.Namespace) -> None:
    root = args.output.resolve()
    source = source_metadata(args.repo)
    if source["source_digest"] != args.source_digest:
        raise SystemExit(f"{args.package} source changed while the artifact was built")
    files = file_inventory(root)
    manifest = common_manifest(
        package=args.package,
        version=args.version,
        platform=args.platform,
        source=source,
        files=files,
    )
    manifest.update(
        {
            "abi": "cxx17-grpc-debian13",
            "contract": contract_binding(args.contract_manifest.resolve()),
            "schema_version": 1,
            "source_sha256": source["source_digest"],
        }
    )
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    manifest_path = root / "manifest.json"
    manifest = load_json(manifest_path)
    expected = {
        "artifact_channel": "development",
        "package": args.package,
        "platform": args.platform,
        "version": args.version,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise SystemExit(f"development artifact identity mismatch: {root}")
    source = manifest.get("development_source_digest")
    if source != {"algorithm": "sha256", "hex": args.source_digest}:
        raise SystemExit(f"development artifact source digest mismatch: {root}")
    if GIT_HEAD.fullmatch(str(manifest.get("source_head", ""))) is None:
        raise SystemExit(f"development artifact source HEAD is invalid: {root}")
    if manifest.get("source_tree_state") not in {"clean", "dirty"}:
        raise SystemExit(f"development artifact tree state is invalid: {root}")
    files = manifest.get("files")
    if not isinstance(files, dict) or files != file_inventory(root):
        raise SystemExit(f"development artifact file inventory mismatch: {root}")
    if manifest.get("artifact_digest") != artifact_digest(files):
        raise SystemExit(f"development artifact digest mismatch: {root}")
    if args.contract_manifest is not None:
        if manifest.get("contract") != contract_binding(
            args.contract_manifest.resolve()
        ):
            raise SystemExit(f"development artifact contract mismatch: {root}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    subparsers = root.add_subparsers(dest="command", required=True)

    source = subparsers.add_parser("source-meta")
    source.add_argument("--repo", type=Path, required=True)
    source.add_argument(
        "--field",
        choices=(
            "source_commit",
            "source_digest",
            "source_head",
            "source_tree_state",
        ),
    )

    contract = subparsers.add_parser("finalize-contract")
    contract.add_argument("--repo", type=Path, required=True)
    contract.add_argument("--output", type=Path, required=True)
    contract.add_argument("--version", required=True)
    contract.add_argument("--platform", required=True)
    contract.add_argument("--source-digest", required=True)

    component = subparsers.add_parser("finalize-component")
    component.add_argument("--repo", type=Path, required=True)
    component.add_argument("--output", type=Path, required=True)
    component.add_argument("--package", required=True)
    component.add_argument("--version", required=True)
    component.add_argument("--platform", required=True)
    component.add_argument("--source-digest", required=True)
    component.add_argument("--contract-manifest", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--root", type=Path, required=True)
    verify_parser.add_argument("--package", required=True)
    verify_parser.add_argument("--version", required=True)
    verify_parser.add_argument("--platform", required=True)
    verify_parser.add_argument("--source-digest", required=True)
    verify_parser.add_argument("--contract-manifest", type=Path)
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "source-meta":
        metadata = source_metadata(args.repo)
        print(metadata[args.field] if args.field else json.dumps(metadata, sort_keys=True))
    elif args.command == "finalize-contract":
        finalize_contract(args)
    elif args.command == "finalize-component":
        finalize_component(args)
    elif args.command == "verify":
        verify(args)
    else:
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
