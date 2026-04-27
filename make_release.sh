#!/usr/bin/env bash
# make_release.sh — build a self-contained zip a brand-new person can run.
#
# Bundles:
#   - All project code (this repo)
#   - trail/ (TRAIL paper source, with the trail symlink collapsed)
#   - trail/TKG_data/otx_dataset_timestamped/ (graph the default ensemble runs over)
#   - trail/src/weights/2-layer/ (paper baseline checkpoints)
#   - sandbox/year_drop/B/weights/fold0..4.pt (our re-trained ensemble)
#   - setup.sh
#
# Excludes (to keep size ~600 MB instead of multi-GB):
#   - .venv, .git, __pycache__, .DS_Store, *.pyc
#   - trail/TKG.zip, trail/ML_DATA.zip (redundant compressed copies)
#   - trail/TKG_data/otx_dataset/ (untimestamped graph — only used by
#     USE_PAPER_BASELINE=1; ~680 MB, dropped to keep the zip small)
#   - trail/model_weights/ (~300 MB of other-layer variants, unused)
#   - archive/, logs/, htmlstuff/, extras/
#   - other sandbox/year_drop/{A,C,D}/ configs
#
# Recipient workflow:
#   unzip MASTER_CAPSTONE_release.zip
#   cd MASTER_CAPSTONE
#   ./setup.sh                              # creates venv, installs deps
#   source .venv/bin/activate
#   python3 -m uvicorn predict_paper_server:app --host 0.0.0.0 --port 47823

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PARENT="$(dirname "$ROOT")"
NAME="$(basename "$ROOT")"
STAGE="$(mktemp -d -t trail_release_XXXXXX)"
OUT="$PARENT/${NAME}_release.zip"

echo "[1/4] staging at $STAGE/$NAME"
trap 'rm -rf "$STAGE"' EXIT

# rsync into the staging dir, dereferencing symlinks (-L) so trail/ becomes
# a real directory in the output.
rsync -aL \
  --exclude='.venv/' \
  --exclude='.git/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='.claude/' \
  --exclude='.idea/' \
  --exclude='.vscode/' \
  --exclude='node_modules/' \
  --exclude='archive/' \
  --exclude='logs/' \
  --exclude='extras/' \
  --exclude='htmlstuff/' \
  --exclude='trail_original/' \
  --exclude='trail/TKG.zip' \
  --exclude='trail/ML_DATA.zip' \
  --exclude='trail/TKG_data/otx_dataset/' \
  --exclude='trail/model_weights/' \
  --exclude='sandbox/year_drop/A/' \
  --exclude='sandbox/year_drop/C/' \
  --exclude='sandbox/year_drop/D/' \
  --exclude='sandbox/year_drop/*/predictions/' \
  --exclude='sandbox/year_drop/*.npz' \
  --exclude='sandbox/year_drop/*.json' \
  --exclude='sandbox/year_drop/*.log' \
  --exclude='trail_gnn/models/*/' \
  --exclude='*.dump' \
  --exclude='/tmp/' \
  --exclude='**/otx_checkpoint*.json' \
  --exclude='*.env' \
  --exclude='.env' \
  "$ROOT/" "$STAGE/$NAME/"

echo "[2/4] verifying required files in stage"
REQ=(
  "$STAGE/$NAME/predict_paper_server.py"
  "$STAGE/$NAME/setup.sh"
  "$STAGE/$NAME/trail_gnn/requirements.txt"
  "$STAGE/$NAME/trail/src/models/gnn.py"
  "$STAGE/$NAME/trail/TKG_data/otx_dataset_timestamped/full_graph_csr.pt"
  "$STAGE/$NAME/sandbox/year_drop/B/weights/fold0.pt"
  "$STAGE/$NAME/sandbox/year_drop/B/weights/fold4.pt"
)
for f in "${REQ[@]}"; do
  if [ ! -e "$f" ]; then
    echo "  MISSING: $f"
    echo "  Aborting — release would not run on a fresh machine."
    exit 1
  fi
done
echo "  all required files present"

echo "[3/4] sizing"
du -sh "$STAGE/$NAME"

echo "[4/4] zipping → $OUT"
rm -f "$OUT"
( cd "$STAGE" && zip -r -q "$OUT" "$NAME" )
ls -lh "$OUT"

echo
echo "Done. Ship $OUT."
echo "Recipient runs:"
echo "  unzip $(basename "$OUT")"
echo "  cd $NAME"
echo "  ./setup.sh"
echo "  source .venv/bin/activate"
echo "  python3 -m uvicorn predict_paper_server:app --host 0.0.0.0 --port 47823"
