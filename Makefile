PYTHON ?= python3
export NASM ?= nasm
export QEMU ?= qemu-system-x86_64

.PHONY: all build dash disk install-iso run run_file run_install libc-audit license-audit binutils-smoke run run_vga run_real_mode debug smoke clean
all: build

build:
	$(PYTHON) scripts/build.py

dash: build
	$(PYTHON) scripts/build_dash.py

disk:
	$(PYTHON) scripts/make_work_disk.py

install-iso: build dash
	$(PYTHON) scripts/build_install_iso.py

libc-audit: build
	$(PYTHON) scripts/libc_audit.py

license-audit: build
	$(PYTHON) scripts/license_audit.py

# Explicit prepared Seed: ordinary build/smoke never downloads GNU sources.
binutils-smoke: build
	$(PYTHON) tests/binutils_smoke.py --seed-manifest "$(SEED_MANIFEST)"

run: install-iso
	$(PYTHON) scripts/run_qemu.py --install-iso

run_file: build
	$(PYTHON) scripts/run_qemu.py --iso-file

run_install: install-iso
	$(PYTHON) scripts/run_qemu.py --install-iso

run_iso: build
	$(PYTHON) scripts/run_qemu.py --iso

run_floppy: build
	$(PYTHON) scripts/run_qemu.py

run_vga: build
	$(PYTHON) scripts/run_qemu.py --iso --vga

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

# Public-threading candidate: explicitly supplied, verified upstream sources.
THREADING_NEWLIB_PREFIX ?= .cache/xos_seed/threading_newlib/prefix
GCC_SOURCE ?= .cache/xos_seed/threading_sources/gcc-16.2.0
.PHONY: threading-newlib threading-sdk threading-probes threading-smoke
threading-newlib:
	$(PYTHON) scripts/build_threading_newlib.py --archive "$(NEWLIB_ARCHIVE)"
threading-sdk:
	$(PYTHON) scripts/build_threading_sdk.py --newlib-prefix "$(THREADING_NEWLIB_PREFIX)" --gcc-source "$(GCC_SOURCE)" --cpp
threading-probes:
	$(PYTHON) scripts/build_threading_probes.py
# Keep the shared build stages and guest checks sequential even under make -j.
threading-smoke:
	$(PYTHON) scripts/build.py
	$(PYTHON) scripts/build_threading_sdk.py --newlib-prefix "$(THREADING_NEWLIB_PREFIX)" --gcc-source "$(GCC_SOURCE)" --cpp
	$(PYTHON) scripts/build_threading_probes.py
	$(PYTHON) tests/threading_compile_checks.py
	$(PYTHON) tests/threading_smoke.py
	$(PYTHON) tests/threading_pthread_smoke.py
	$(PYTHON) tests/threading_cpp_smoke.py
	$(PYTHON) tests/process_smoke.py
	$(PYTHON) tests/runtime_smoke.py
	$(PYTHON) tests/task_smoke.py
	$(PYTHON) tests/libc_smoke.py
	$(PYTHON) tests/persist_smoke.py
	$(PYTHON) scripts/license_audit.py
	$(PYTHON) scripts/threading_qualification.py
