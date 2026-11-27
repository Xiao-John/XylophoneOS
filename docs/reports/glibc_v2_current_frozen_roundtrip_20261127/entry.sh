#!/bin/sh
set -eu
mkdir -p /scratch/tmp /scratch/deny-build /workspace/build/host_tools/linux-aarch64
export TMPDIR=/scratch/tmp
cp /fat-cached/work_disk_host /fat-cached/work_disk_host.sha256 /workspace/build/host_tools/linux-aarch64/
cp -r /cached /scratch/tmp/xos_xypm_host_0
chmod 700 /scratch/tmp/xos_xypm_host_0 /scratch/tmp/xos_xypm_host_0/*
for exe in clang++ c++ g++ gcc make; do
  printf '#!/bin/sh\nprintf "compiler invocation is forbidden in this replay\\n" >&2\nexit 99\n' > "/scratch/deny-build/$exe"
  chmod +x "/scratch/deny-build/$exe"
done
export PATH="/scratch/deny-build:$PATH"
collect() {
  for file in /scratch/guest/*serial.log; do
    if test -f "$file"; then gzip -nc "$file" > "/out/$(basename "$file").gz"; fi
  done
  df -h /scratch /workspace/build
}
trap collect EXIT
cd /workspace
PYTHONPATH=/workspace/scripts:/workspace/tests python3 -B /out/replay.py "$@"
