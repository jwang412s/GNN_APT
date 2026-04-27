#!/usr/bin/env bash
# setup.sh — one-shot setup for /attribute on a fresh machine.
#
# What this does:
#   1. Resolves ./trail (handles dangling symlink from a zip transfer)
#   2. Clones the TRAIL paper repo if missing
#   3. Downloads + unpacks the TKG dataset and paper weights if missing
#   4. Verifies our re-trained fold checkpoints are present
#   5. Creates .venv and installs Python dependencies
#   6. Prints the exact command to start the server
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
#
# Re-running is safe — every step is idempotent.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "[1/6] Checking ./trail layout"
if [ -L trail ] && [ ! -e trail ]; then
  echo "  ./trail is a dangling symlink — removing"
  rm trail
fi
if [ -L trail ]; then
  TARGET="$(readlink trail)"
  echo "  ./trail -> $TARGET (collapsing to a real directory)"
  rm trail
  if [ -d "$TARGET" ]; then
    cp -R "$TARGET" trail
  fi
fi

echo "[2/6] Cloning TRAIL paper repo if missing"
if [ ! -d trail ]; then
  git clone https://github.com/HewlettPackard/TRAIL.git trail
else
  echo "  ./trail already present — skipping clone"
fi

echo "[3/6] TKG dataset"
TKG_TS="trail/TKG_data/otx_dataset_timestamped/full_graph_csr.pt"
TKG_ORIG="trail/TKG_data/otx_dataset/full_graph_csr.pt"
if [ ! -f "$TKG_TS" ] && [ ! -f "$TKG_ORIG" ]; then
  cat <<EOF
  TKG data not found.

  If you got this folder as the official release zip, the TKG should
  already be inside trail/TKG_data/ — something is wrong with the zip.

  If you cloned this repo from GitHub instead, the TKG is hosted out-
  of-band by the TRAIL paper authors. See trail/README.md for the
  current download link, then unpack TKG.zip into trail/TKG_data/ so
  that one of these files exists:

    $TKG_TS         (preferred — needed for the default ensemble)
    $TKG_ORIG       (only needed for USE_PAPER_BASELINE=1)

  Re-run ./setup.sh once that's done.
EOF
  exit 1
else
  echo "  TKG present"
fi

echo "[4/6] Model checkpoints"
WDIR="sandbox/year_drop/B/weights"
MISSING=0
for i in 0 1 2 3 4; do
  if [ ! -f "$WDIR/fold${i}.pt" ]; then
    echo "  missing: $WDIR/fold${i}.pt"
    MISSING=1
  fi
done
if [ "$MISSING" -eq 1 ]; then
  cat <<EOF

  Re-trained fold checkpoints are missing from $WDIR.

  Options:
    (a) Ask whoever shipped you this folder for the fold0..fold4.pt files
        and drop them into $WDIR/.
    (b) Run the paper authors' single-fold checkpoint instead — set
        USE_PAPER_BASELINE=1 when starting the server, and make sure
        trail/src/weights/2-layer/gnn_train-0.777_max_lprop+feats+ae-new-data.pt
        exists.
EOF
  exit 1
else
  echo "  fold0..fold4 present"
fi

echo "[5/6] Python venv + dependencies"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r trail_gnn/requirements.txt

echo "[6/6] Done."
cat <<'EOF'

To start the server:
  source .venv/bin/activate
  python3 -m uvicorn predict_paper_server:app --host 0.0.0.0 --port 47823

Test /attribute once "[ready] server up." appears:
  curl -X POST http://localhost:47823/attribute \
       -H "Content-Type: application/json" \
       -d '{"iocs": [{"type":"domain","value":"suspicious.example.com"}]}'
EOF
