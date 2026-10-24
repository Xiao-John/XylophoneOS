PYTHON ?= python3
export NASM ?= nasm
export QEMU ?= qemu-system-x86_64

.PHONY: all build disk libc-audit license-audit binutils-smoke run run_vga run_real_mode debug smoke clean
all: build

build:
	$(PYTHON) scripts/build.py

disk:
	$(PYTHON) scripts/make_work_disk.py

libc-audit: build
	$(PYTHON) scripts/libc_audit.py

license-audit: build
	$(PYTHON) scripts/license_audit.py

# Explicit prepared Seed: ordinary build/smoke never downloads GNU sources.
binutils-smoke: build
	$(PYTHON) tests/binutils_smoke.py --seed-manifest "$(SEED_MANIFEST)"

run: build
	$(PYTHON) scripts/run_qemu.py

run_vga: build
	$(PYTHON) scripts/run_qemu.py --vga

run_real_mode: build
	$(PYTHON) scripts/run_qemu.py --real-mode

debug: build
	$(PYTHON) scripts/run_qemu.py --debug-port 1234

smoke: build
	$(PYTHON) tests/boot_smoke.py
	$(PYTHON) tests/kernel_smoke.py
	$(PYTHON) tests/task_smoke.py
	$(PYTHON) tests/process_smoke.py
	$(PYTHON) tests/file_smoke.py
	$(PYTHON) tests/persist_smoke.py
	$(PYTHON) tests/full_disk_smoke.py
	$(PYTHON) tests/libc_smoke.py
	$(PYTHON) tests/e08_storage_smoke.py
	$(PYTHON) tests/runtime_smoke.py
	$(PYTHON) scripts/license_audit.py

clean:
	$(PYTHON) scripts/build.py --clean
