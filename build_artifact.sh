#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "$0")" && pwd)"
workspace_root="${RL_TRAINING_WORKSPACE:-$(cd "${repo_dir}/.." && pwd)}"
artifact_root="${workspace_root}/.workspace/artifacts/rl-contracts"
version="$(tr -d '[:space:]' < "${repo_dir}/VERSION")"
source_commit="$(git -C "${repo_dir}" rev-parse --short=12 HEAD)"
platform="$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')"
platform_dir="${platform//\//-}"

hash_file() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        sha256sum "$1" | awk '{print $1}'
    fi
}

source_sha256="$(hash_file "${repo_dir}/proto/v1/maze.proto")"
source_id="${source_commit}"
if ! git -C "${repo_dir}" diff --quiet ||
   ! git -C "${repo_dir}" diff --cached --quiet ||
   test -n "$(git -C "${repo_dir}" ls-files --others --exclude-standard)"; then
    source_id="${source_commit}-dirty-${source_sha256:0:12}"
fi

output_dir="${artifact_root}/${version}/${platform_dir}"
temp_dir="${workspace_root}/.workspace/artifacts/.tmp-contracts-$$"
builder_image="rl-training/contracts-builder:${version}"

if test -d "${output_dir}"; then
    if PACKAGE_VERSION="${version}" \
       SOURCE_ID="${source_id}" \
       SOURCE_SHA256="${source_sha256}" \
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
    "source_id": os.environ["SOURCE_ID"],
    "source_sha256": os.environ["SOURCE_SHA256"],
    "platform": os.environ["PLATFORM"],
}
if any(manifest.get(key) != value for key, value in expected.items()):
    raise SystemExit(1)
for relative, checksum in manifest.get("files", {}).items():
    path = root / relative
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
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

manifest = {
    "schema_version": 1,
    "package": "rl-contracts",
    "version": os.environ["CONTRACT_VERSION"],
    "source_commit": os.environ["SOURCE_COMMIT"],
    "source_id": os.environ["SOURCE_ID"],
    "source_sha256": os.environ["SOURCE_SHA256"],
    "platform": os.environ["PLATFORM"],
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
