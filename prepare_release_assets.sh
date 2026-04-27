#!/usr/bin/env bash
# prepare_release_assets.sh — package and upload the binary assets that
# git can't carry, so that `git clone` + ./setup.sh is enough on a fresh PC.
#
# What this uploads as a GitHub Release named "assets-v1":
#   - fold0.pt..fold4.pt       (our re-trained ensemble, ~50 MB total)
#   - tkg_timestamped.tar.gz   (timestamped TKG, ~80 MB compressed)
#   - paper_baseline.tar.gz    (paper authors' 5 single-fold weights, ~50 MB)
#
# Requires: gh (GitHub CLI) authenticated to jwang412s/GNN_APT.
#
# Usage:
#   ./prepare_release_assets.sh

set -euo pipefail

REPO="jwang412s/GNN_APT"
TAG="assets-v1"
ROOT="$(cd "$(dirname "$0")" && pwd)"
STAGE="$(mktemp -d -t trail_assets_XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT

cd "$ROOT"

echo "[1/4] verifying source files exist locally"
REQ=(
  "sandbox/year_drop/B/weights/fold0.pt"
  "sandbox/year_drop/B/weights/fold1.pt"
  "sandbox/year_drop/B/weights/fold2.pt"
  "sandbox/year_drop/B/weights/fold3.pt"
  "sandbox/year_drop/B/weights/fold4.pt"
  "trail/TKG_data/otx_dataset_timestamped/full_graph_csr.pt"
  "trail/src/weights/2-layer"
)
for f in "${REQ[@]}"; do
  if [ ! -e "$f" ]; then
    echo "  MISSING: $f"
    exit 1
  fi
done
echo "  ok"

echo "[2/4] staging assets into $STAGE"
cp sandbox/year_drop/B/weights/fold{0..4}.pt "$STAGE/"
tar -czf "$STAGE/tkg_timestamped.tar.gz" \
    -C trail/TKG_data otx_dataset_timestamped
tar -czf "$STAGE/paper_baseline.tar.gz" \
    -C trail/src/weights 2-layer
ls -lh "$STAGE"

echo "[3/4] checking gh auth"
if ! gh auth status >/dev/null 2>&1; then
  echo "  'gh' is not authenticated. Run: gh auth login"
  exit 1
fi

echo "[4/4] creating release '$TAG' on $REPO"
if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  echo "  release $TAG already exists — uploading assets with --clobber"
  gh release upload "$TAG" \
      "$STAGE/fold0.pt" "$STAGE/fold1.pt" "$STAGE/fold2.pt" \
      "$STAGE/fold3.pt" "$STAGE/fold4.pt" \
      "$STAGE/tkg_timestamped.tar.gz" \
      "$STAGE/paper_baseline.tar.gz" \
      --repo "$REPO" --clobber
else
  gh release create "$TAG" \
      "$STAGE/fold0.pt" "$STAGE/fold1.pt" "$STAGE/fold2.pt" \
      "$STAGE/fold3.pt" "$STAGE/fold4.pt" \
      "$STAGE/tkg_timestamped.tar.gz" \
      "$STAGE/paper_baseline.tar.gz" \
      --repo "$REPO" \
      --title "Binary assets v1 (fold weights + TKG)" \
      --notes "Bundled assets that git can't carry. setup.sh fetches these automatically. Total ~180 MB."
fi

echo
echo "Done. Verify at: https://github.com/$REPO/releases/tag/$TAG"
