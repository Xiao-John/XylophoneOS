#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# XOS release pipeline — stages for 0.0.2-1103+ releases (see docs/releases/playbook.md).
# Usage: scripts/release_pipeline.sh <stage>
# Stages: build | gates | freeze | package | smoke | materials | checksums | status
# Publish (tag/upload) is intentionally NOT automated; run manually after user order.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
V="$(tr -d '[:space:]' < VERSION)"
R="build/releases/$V"
PYTHON="${PYTHON:-python3}"

stage_build() {
  make build
  "$PYTHON" scripts/build_dash.py
  "$PYTHON" scripts/build_install_iso.py
  echo "build_id=$("$PYTHON" -c "import json;print(json.load(open('build/manifest.json'))['build_id'])")"
}

stage_gates() {
  "$PYTHON" scripts/license_audit.py
  # Qt B4/B5 if shipping Qt: see docs/reports/qt_static_distribution_20261103/
}

stage_freeze() {
  mkdir -p "$R"
  cp build/manifest.json "$R/system_manifest.json"
  cp build/xos-install.iso build/xos-install-dash.iso build/install_manifest.json "$R/"
  rm -rf "$R/sdk"
  cp -R build/sdk "$R/sdk"
  echo "frozen $R"
}

stage_package() {
  # Override via env: DASH_MANIFEST, CPYTHON_STAGE, WHEEL, EXTRA_ELFS (space-separated NAME=PATH)
  local dash="${DASH_MANIFEST:?set DASH_MANIFEST to .cache/xos_seed/dash/<key>/manifest.json}"
  local stage="${CPYTHON_STAGE:?set CPYTHON_STAGE to .../stage_py3_b_manifest.json (must include zlib)}"
  local args=(--dash-manifest "$dash" --cpython-stage "$stage")
  if [[ -n "${WHEEL:-}" ]]; then args+=(--wheel-package "$WHEEL"); fi
  # EXTRA_ELFS="cat=path make=path xypm=path"
  for kv in ${EXTRA_ELFS:-}; do
    args+=(--extra-elf "$kv")
  done
  # Refuse if staged outputs exist (packager also checks)
  rm -rf "$R"/xylophoneos_revival_"$V"_images "$R"/xylophoneos_revival_"$V"_sdk
  rm -f "$R"/release_manifest.json "$R"/xylophoneos_revival_"$V"_images.tar.gz "$R"/xylophoneos_revival_"$V"_sdk.tar.gz
  "$PYTHON" scripts/package_release.py "${args[@]}"
}

stage_smoke() {
  "$PYTHON" scripts/release_smoke.py
  "$PYTHON" -c "import json;d=json.load(open('$R/package_smoke_report.json'));assert d['status']=='passed',d.get('error');print('smoke',len(d['checks']),'checks OK')"
}

stage_materials() {
  rm -rf "$R/sources"
  "$PYTHON" scripts/package_release_materials.py
}

stage_checksums() {
  cd "$R"
  rm -f CHECKSUMS.sha256
  local files=(xylophoneos_revival_"$V"_images.tar.gz xylophoneos_revival_"$V"_sdk.tar.gz
    sources/xos-"$V"-sources.tar.gz release_manifest.json system_manifest.json install_manifest.json package_smoke_report.json)
  [[ -f xylophoneos_revival_"$V"_qt6_static.tar.gz ]] && files+=(xylophoneos_revival_"$V"_qt6_static.tar.gz)
  for f in "${files[@]}"; do shasum -a 256 "$f"; done | tee CHECKSUMS.sha256
}

stage_status() {
  echo "version=$V release_dir=$R"
  ls -la "$R"/*.tar.gz "$R"/sources/*.tar.gz 2>/dev/null | awk '{printf "%.1f MB  %s\n",$5/1024/1024,$9}' || true
  [[ -f "$R/package_smoke_report.json" ]] && "$PYTHON" -c "import json;d=json.load(open('$R/package_smoke_report.json'));print('smoke:',d['status'],d.get('checks'))"
  git log --oneline -1
}

case "${1:-}" in
  build) stage_build ;;
  gates) stage_gates ;;
  freeze) stage_freeze ;;
  package) stage_package ;;
  smoke) stage_smoke ;;
  materials) stage_materials ;;
  checksums) stage_checksums ;;
  status) stage_status ;;
  *) echo "usage: $0 {build|gates|freeze|package|smoke|materials|checksums|status}" >&2; exit 2 ;;
esac
