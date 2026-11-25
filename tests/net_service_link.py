#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host-GCC freestanding link check; never an XOS guest/toolchain acceptance."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from lwip_service_build import build
from toolchain import COMMON_FLAGS, X86_FLAGS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    os.environ["XOS_LWIP_SOURCE_ARCHIVE"] = str(args.archive.resolve())
    with tempfile.TemporaryDirectory(prefix="xos_net_link_") as temporary:
        out = Path(temporary)
        sdk = out / "sdk"
        shutil.copytree(root / "src/third_party/newlib/x86_64-elf/include", sdk / "include")
        (sdk / "include/xos").mkdir()
        for folder in ("src/shared/include/xos", "src/user/include/xos"):
            for item in (root / folder).glob("*.hpp"):
                shutil.copyfile(item, sdk / "include/xos" / item.name)

        def run(command):
            subprocess.run(command, check=True)

        objects, includes, _ = build(root, out, sdk, run, shutil.which, X86_FLAGS)
        for name in ("src/user/network/service_core.cpp", "src/user/network/lwip_stack.cpp",
                     "src/user/network/service_loop.cpp", "src/user/programs/net_service.cpp",
                     "src/user/drivers/virtio_net.cpp", "src/user/sdk/text.cpp",
                     "src/user/arch/x86_64/syscall.cpp", "src/shared/runtime/memory.cpp"):
            obj = out / (Path(name).stem + ".o")
            run(["g++", *COMMON_FLAGS, *X86_FLAGS, "-Os", "-ffunction-sections", "-fdata-sections",
                 "-DXOS_NET_STACK=1", "-I", str(sdk / "include"), *includes,
                 "-c", str(root / name), "-o", str(obj)])
            objects.append(str(obj))
        # This GAS entry only roots the real service for host linker QA.
        entry = out / "entry.s"
        entry.write_text('.section .text.entry\n.global _start\n_start:\ncall xos_user_main\nud2\n'
                         '.section .note.GNU-stack,"",@progbits\n')
        run(["gcc", "-c", str(entry), "-o", str(out / "entry.o")])
        run(["g++", "-nostdlib", "-static", "-no-pie", "-Wl,--gc-sections,--no-undefined,--build-id=none,-z,noexecstack",
             "-T", str(root / "src/user/arch/x86_64/user.ld"), str(out / "entry.o"), *objects,
             "-o", str(out / "network.elf")])
        run(["objcopy", "--strip-debug", str(out / "network.elf"), str(out / "network.image.elf")])
        size = (out / "network.image.elf").stat().st_size
        if size > 131072:
            raise AssertionError("network service exceeds immutable image read limit")
        print(f"PASS host-GCC freestanding link, image={size} bytes; frozen target/guest NOT_RUN")


if __name__ == "__main__":
    main()
