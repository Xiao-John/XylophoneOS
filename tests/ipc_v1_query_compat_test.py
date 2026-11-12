# SPDX-License-Identifier: Apache-2.0
"""Run old/current SDK queries through the real kernel query branch on the host.

The old headers come from the fixed public commit in this repository's history.
Only syscall transport, page validity, expiry and counter setup are host hooks;
the ABI headers, SDK wrappers and kernel query logic are not reimplemented.
This is an ABI compatibility regression, not scheduling or guest qualification.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

repo_root = Path(__file__).resolve().parents[1]
baseline_commit = "e6246faf8eefac305a99528f727b1592ee93a5b2"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=repo_root / "src/kernel/arch/x86_64/tasks.cpp")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="xos_ipc_query_compat_") as temporary:
        directory = Path(temporary)
        write_headers(directory)
        kernel = directory / "kernel.cpp"
        kernel.write_text(kernel_source(args.source.read_text()))
        compiler = os.environ.get("CXX", "c++")
        common = [compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror"]
        obj = directory / "kernel.o"
        subprocess.run([*common, "-I", str(directory / "new"), "-c", str(kernel),
                        "-o", str(obj)], check=True)
        for revision in ("old", "new"):
            client = directory / f"{revision}.cpp"
            client.write_text(client_source(revision))
            binary = directory / f"{revision}_query"
            subprocess.run([*common, "-I", str(directory / revision), str(client),
                            str(obj), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
    print("IPC_V1_QUERY_COMPAT_CASES_PASSED=9")


def definition(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[start:end] + "\n"


def write_headers(directory):
    paths = {
        "abi_types.hpp": "src/shared/include/xos/abi_types.hpp",
        "ipc_v1_abi.hpp": "src/shared/include/xos/ipc_v1_abi.hpp",
        "ipc_v1.hpp": "src/user/include/xos/ipc_v1.hpp",
    }
    for revision in ("old", "new"):
        headers = directory / revision / "xos"
        headers.mkdir(parents=True)
        for name, path in paths.items():
            contents = (subprocess.check_output(
                ["git", "show", f"{baseline_commit}:{path}"], cwd=repo_root, text=True)
                if revision == "old" else (repo_root / path).read_text())
            (headers / name).write_text(contents)
        (headers / "sdk.hpp").write_text(
            "#pragma once\nnamespace xos::sdk { "
            "i64 syscall(u64 number,u64 first=0,u64 second=0,u64 third=0); }\n")


def kernel_source(source):
    signatures = (
        "void copy_bytes(void* destination, const void* source, u64 length) {",
        "void copy_from_user(void* destination, u64 source, u64 length) {",
        "void copy_to_user(u64 destination, const void* source, u64 length) {",
        "bool ipc_v1_header_valid(const ipc_v1_header& header, u32 expected) {",
    )
    helpers = "\n".join(definition(source, value) for value in signatures)
    start = source.index("void* ipc_v1_syscall(interrupt_frame* frame) {")
    signature = "if (action == static_cast<u64>(ipc_v1_action::query_features)) {"
    query_start = source.index(signature, start)
    query = source[start:query_start] + definition(source[query_start:], signature)
    # Distinct C++ namespaces allow old/new ABI types in separate translation units.
    return r"""
#define xos kernelxos
#include <xos/ipc_v1_abi.hpp>
#undef xos
using namespace kernelxos;
struct interrupt_frame { u64 rax=0; u64 rdi=0; u64 rsi=0; u64 rdx=0; };
u64 ipc_v1_direct_switch_count=0;
void expire_waiters() {}
bool user_range_ok(u64 address,u64 length,bool) {
    return address!=0 && length==sizeof(ipc_v1_feature_query);
}
""" + helpers + query + r"""
    return nullptr;
}
extern "C" i64 kernel_query(u64 action,u64 address,u64 flags,u64 count) {
    ipc_v1_direct_switch_count=count;
    interrupt_frame frame{};
    frame.rdi=action; frame.rsi=address; frame.rdx=flags;
    if (ipc_v1_syscall(&frame)==nullptr) return 777;
    return static_cast<i64>(frame.rax);
}
"""


def client_source(revision):
    preamble = r"""
#include <xos/ipc_v1.hpp>
#include <cassert>
using namespace xos;
extern "C" i64 kernel_query(u64,u64,u64,u64);
u64 counter=0;
namespace xos::sdk {
i64 syscall(u64 number,u64 action,u64 address,u64 flags) {
    assert(number==sys_ipc_v1);
    return kernel_query(action,address,flags,counter);
}
}
int main() {
    for(counter=0; counter<2; ++counter) {
        ipc_v1_feature_query query{};
        assert(ipc_v1::query_features(query)==0);
        assert(query.supported_features==0x0f);
"""
    if revision == "old":
        return preamble + r"""
        assert(query.reserved[0]==0 && query.reserved[1]==0);
    }
}
"""
    return preamble + r"""
        assert(query.direct_switch_count==0 && query.reserved==0);
        assert(ipc_v1::query_features(query,true)==0);
        assert(query.supported_features==0x0f);
        assert(query.direct_switch_count==counter && query.reserved==0);
    }
    for(u64 flags=2; flags<4; ++flags) {
        ipc_v1_feature_query query{};
        query.header.version=ipc_v1_version; query.header.size=sizeof(query);
        assert(sdk::syscall(sys_ipc_v1,static_cast<u64>(ipc_v1_action::query_features),
                            reinterpret_cast<u64>(&query),flags)==
               static_cast<i64>(ipc_v1_error::invalid_argument));
    }
    ipc_v1_endpoint_create request{};
    request.header.version=ipc_v1_version; request.header.size=sizeof(request);
    assert(sdk::syscall(sys_ipc_v1,static_cast<u64>(ipc_v1_action::endpoint_create),
                        reinterpret_cast<u64>(&request),ipc_v1_query_flag_direct_switch_count)==
           static_cast<i64>(ipc_v1_error::invalid_argument));
}
"""


if __name__ == "__main__":
    main()
