#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "$0")" && pwd)"
workspace_root="${RL_TRAINING_WORKSPACE:-$(cd "${repo_dir}/.." && pwd)}"
artifact_root="${workspace_root}/.workspace/artifacts/rl-contracts"
version="$(tr -d '[:space:]' < "${repo_dir}/VERSION")"
source_commit="$(git -C "${repo_dir}" rev-parse --short=12 HEAD)"
source_status="$(git -C "${repo_dir}" status --porcelain --untracked-files=all)"
if test -n "${source_status}"; then
    echo "refusing to create or reuse a contracts artifact from a dirty worktree" >&2
    echo "commit the reviewed source first, then rerun this command" >&2
    exit 1
fi
source_tree_state="clean"
platform="$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')"
platform_dir="${platform//\//-}"

source_sha256="$(python3 - \
    "${repo_dir}/proto/v1/common.proto" \
    "${repo_dir}/proto/v1/training.proto" \
    "${repo_dir}/proto/v1/maze_task.proto" \
    "${repo_dir}/schemas/maze.metrics.v4.json" \
    "${repo_dir}/schemas/maze.metrics.v4.sha256" <<'PY'
import hashlib
import sys
from pathlib import Path

digest = hashlib.sha256()
for raw in sys.argv[1:]:
    path = Path(raw)
    digest.update(path.name.encode("utf-8"))
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")
print(digest.hexdigest())
PY
)"
source_id="contract-source-${source_sha256:0:16}"

output_dir="${artifact_root}/${version}/${platform_dir}"
temp_dir="${workspace_root}/.workspace/artifacts/.tmp-contracts-$$"
builder_image="rl-training/contracts-builder:${version}"

if test -d "${output_dir}"; then
    if PACKAGE_VERSION="${version}" \
       SOURCE_ID="${source_id}" \
       SOURCE_SHA256="${source_sha256}" \
       SOURCE_COMMIT="${source_commit}" \
       PLATFORM="${platform}" \
       python3 - "${output_dir}" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest_path = root / "manifest.json"
if not manifest_path.is_file():
    raise SystemExit(1)
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
expected = {
    "package": "rl-contracts",
    "version": os.environ["PACKAGE_VERSION"],
    "platform": os.environ["PLATFORM"],
    "source_commit": os.environ["SOURCE_COMMIT"],
    "source_tree_state": "clean",
}
if any(manifest.get(key) != value for key, value in expected.items()):
    raise SystemExit(1)
if manifest.get("schema_version") != 2:
    raise SystemExit(1)
source = manifest.get("source_digest", {})
if source != {"algorithm": "sha256", "hex": os.environ["SOURCE_SHA256"]}:
    raise SystemExit(1)
files = manifest.get("files", {})
for relative, checksum in files.items():
    path = root / relative
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise SystemExit(1)
canonical_files = json.dumps(
    files, separators=(",", ":"), sort_keys=True
).encode("utf-8")
artifact = manifest.get("artifact_digest", {})
if artifact != {
    "algorithm": "sha256",
    "hex": hashlib.sha256(canonical_files).hexdigest(),
}:
    raise SystemExit(1)
generator_path = root / "generator-identity.json"
if not generator_path.is_file():
    raise SystemExit(1)
generator_metadata = json.loads(generator_path.read_text(encoding="utf-8"))
generator_identity = hashlib.sha256(
    json.dumps(
        generator_metadata, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
).hexdigest()
if manifest.get("generator_identity") != generator_identity:
    raise SystemExit(1)
if manifest.get("contract_packages") != [
    "rl.common.v1",
    "rl.training.v1",
    "rl.task.maze.v1",
]:
    raise SystemExit(1)
catalog_path = root / "schemas/maze.metrics.v4.json"
catalog_digest_path = root / "schemas/maze.metrics.v4.sha256"
if not catalog_path.is_file() or not catalog_digest_path.is_file():
    raise SystemExit(1)
catalog_digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
if catalog_digest_path.read_text(encoding="utf-8").strip() != catalog_digest:
    raise SystemExit(1)
if manifest.get("metric_schemas") != {
    "maze.metrics.v4": {
        "canonical_digest": {
            "algorithm": "sha256",
            "hex": catalog_digest,
        },
        "digest_path": "schemas/maze.metrics.v4.sha256",
        "path": "schemas/maze.metrics.v4.json",
        "schema_version": 4,
    }
}:
    raise SystemExit(1)
PY
    then
        printf '%s\n' "${output_dir}"
        exit 0
    fi
    echo "contract artifact version already exists with different content: ${output_dir}" >&2
    echo "remove that generated artifact explicitly or increment VERSION" >&2
    exit 1
fi

mkdir -p "${temp_dir}" "$(dirname "${output_dir}")"
trap 'rm -rf "${temp_dir}"' EXIT

docker build \
    --file "${repo_dir}/Dockerfile.build" \
    --tag "${builder_image}" \
    "${repo_dir}"

docker run --rm \
    --volume "${repo_dir}:/source:ro" \
    --volume "${temp_dir}:/output" \
    "${builder_image}"

CONTRACT_VERSION="${version}" \
SOURCE_COMMIT="${source_commit}" \
SOURCE_TREE_STATE="${source_tree_state}" \
SOURCE_ID="${source_id}" \
SOURCE_SHA256="${source_sha256}" \
PLATFORM="${platform}" \
OUTPUT_DIR="${temp_dir}" \
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["OUTPUT_DIR"])
files = {}
for path in sorted(root.rglob("*")):
    if path.is_file():
        files[str(path.relative_to(root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

canonical_files = json.dumps(
    files, separators=(",", ":"), sort_keys=True
).encode("utf-8")
artifact_sha256 = hashlib.sha256(canonical_files).hexdigest()
generator_metadata = json.loads(
    (root / "generator-identity.json").read_text(encoding="utf-8")
)
generator_identity = hashlib.sha256(
    json.dumps(
        generator_metadata, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
).hexdigest()
catalog_path = root / "schemas/maze.metrics.v4.json"
catalog_digest_path = root / "schemas/maze.metrics.v4.sha256"
catalog_digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
if catalog_digest_path.read_text(encoding="utf-8").strip() != catalog_digest:
    raise SystemExit("maze.metrics.v4 catalog digest mismatch")

manifest = {
    "schema_version": 2,
    "package": "rl-contracts",
    "version": os.environ["CONTRACT_VERSION"],
    "source_commit": os.environ["SOURCE_COMMIT"],
    "source_tree_state": os.environ["SOURCE_TREE_STATE"],
    "source_id": os.environ["SOURCE_ID"],
    "source_digest": {
        "algorithm": "sha256",
        "hex": os.environ["SOURCE_SHA256"],
    },
    "artifact_digest": {
        "algorithm": "sha256",
        "hex": artifact_sha256,
    },
    "platform": os.environ["PLATFORM"],
    "generator_identity": generator_identity,
    "contract_packages": [
        "rl.common.v1",
        "rl.training.v1",
        "rl.task.maze.v1",
    ],
    "metric_schemas": {
        "maze.metrics.v4": {
            "canonical_digest": {
                "algorithm": "sha256",
                "hex": catalog_digest,
            },
            "digest_path": "schemas/maze.metrics.v4.sha256",
            "path": "schemas/maze.metrics.v4.json",
            "schema_version": 4,
        }
    },
    "files": files,
}
(root / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

mv "${temp_dir}" "${output_dir}"
trap - EXIT
printf '%s\n' "${output_dir}"
