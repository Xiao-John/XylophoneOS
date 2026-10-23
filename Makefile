PYTHON ?= python3
export NASM ?= nasm
export QEMU ?= qemu-system-x86_64

.PHONY: all build disk libc-audit run run_vga run_real_mode debug smoke clean
all: build

build:
	$(PYTHON) scripts/build.py

disk:
	$(PYTHON) scripts/make_work_disk.py

libc-audit: build
	$(PYTHON) scripts/libc_audit.py

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

clean:
	$(PYTHON) scripts/build.py --clean
