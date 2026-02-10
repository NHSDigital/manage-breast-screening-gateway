#!/usr/bin/env bash
#
# Package the Manage Breast Screening Gateway for VM deployment.
#
# Produces a zip archive named gateway-<git-short-hash>.zip containing
# everything needed to run `uv sync --frozen` and launch the services
# on a target VM without Docker.
#
# A SHA256 checksum file is generated alongside the archive for integrity
# verification. For cryptographic signing, use GitHub Artifact Attestations
# in the CI workflow (actions/attest-build-provenance).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUTPUT_DIR="${1:-$REPO_ROOT/dist}"

# ── Prerequisites ──────────────────────────────────────────────────────────────

if ! command -v git &>/dev/null; then
    echo "Error: git is not installed." >&2
    exit 1
fi

if ! command -v zip &>/dev/null; then
    echo "Error: zip is not installed." >&2
    exit 1
fi

if ! command -v unzip &>/dev/null; then
    echo "Error: unzip is not installed." >&2
    exit 1
fi

if ! git -C "$REPO_ROOT" rev-parse --git-dir &>/dev/null; then
    echo "Error: $REPO_ROOT is not a git repository." >&2
    exit 1
fi

# ── Dirty tree warning ────────────────────────────────────────────────────────

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
    echo "Warning: working tree has uncommitted changes." >&2
    echo "         The git hash will not reflect the actual contents." >&2
    echo ""
fi

# ── Version from Git ──────────────────────────────────────────────────────────

SHORT_HASH="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
ARTIFACT_NAME="gateway-${SHORT_HASH}.zip"

echo "========================================"
echo "Packaging Gateway Release"
echo "========================================"
echo "Commit:  ${SHORT_HASH}"
echo "Output:  ${OUTPUT_DIR}/${ARTIFACT_NAME}"
echo ""

# ── Validate required files ───────────────────────────────────────────────────

REQUIRED_FILES=("src" "pyproject.toml" "uv.lock" "README.md")

for item in "${REQUIRED_FILES[@]}"; do
    if [[ ! -e "${REPO_ROOT}/${item}" ]]; then
        echo "Error: required path '${item}' not found in repository root." >&2
        exit 1
    fi
done

# ── Build the archive ────────────────────────────────────────────────────────

mkdir -p "$OUTPUT_DIR"
ARTIFACT_PATH="${OUTPUT_DIR}/${ARTIFACT_NAME}"

# Remove existing artifact if present
rm -f "$ARTIFACT_PATH"

cd "$REPO_ROOT"

# Use git archive to produce a zip containing only the paths needed for deployment.
# This ensures only tracked files are included, preventing accidental inclusion of
# .env files, local secrets, or untracked files.
echo "Creating archive from git tracked files..."
git archive --format=zip -o "$ARTIFACT_PATH" HEAD src/ pyproject.toml uv.lock README.md

echo "Archive created successfully."

# ── Verify archive integrity ─────────────────────────────────────────────────

if ! unzip -t "$ARTIFACT_PATH" > /dev/null 2>&1; then
    echo "Error: archive integrity check failed." >&2
    exit 1
fi

# ── Generate SHA256 checksum ──────────────────────────────────────────────────

CHECKSUM_PATH="${ARTIFACT_PATH}.sha256"
(cd "$OUTPUT_DIR" && shasum -a 256 "$ARTIFACT_NAME" > "${ARTIFACT_NAME}.sha256")

# ── Summary ───────────────────────────────────────────────────────────────────

ARTIFACT_SIZE="$(du -h "$ARTIFACT_PATH" | cut -f1)"

echo ""
echo "========================================"
echo "Package Complete"
echo "========================================"
echo "Artifact: ${ARTIFACT_PATH}"
echo "Checksum: ${CHECKSUM_PATH}"
echo "Size:     ${ARTIFACT_SIZE}"
echo "SHA256:   $(cut -d' ' -f1 "$CHECKSUM_PATH")"
echo ""
echo "Contents:"
zipinfo -1 "$ARTIFACT_PATH" | head -20
TOTAL_FILES="$(zipinfo -t "$ARTIFACT_PATH" 2>&1 | grep -oE '[0-9]+ files')"
echo "..."
echo "Total: ${TOTAL_FILES}"
