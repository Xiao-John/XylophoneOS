// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/dynamic_abi.hpp>
#include <xos/elf.hpp>

namespace xos::dynamic {
enum class error : u32 {
    none, io, bounds, header, identity, role, interpreter, writable_identity,
    digest, sdk, budget, path, duplicate, dependency, cycle, state, revoked, stale
};

bool identity_valid(const object_identity& identity, object_role role, const u8 (&toolchain)[32]);
// read must keep the same read-only pinned object for the entire call. This
// validates identity and its ELF carrier, not relocation or symbol tables.
error inspect_identity(elf::read_exact_fn read, void* context, u64 bytes,
                       const object_identity& expected);
error verify_object(elf::read_exact_fn read, void* context, const generation_object& expected);
struct generation_root { u64 id; u8 sha256[32]; };
// The digest and SDK identity must originate in the caller's trusted image or
// authenticated activation controller. An adjacent writable file is no trust root.
error read_generation(elf::read_exact_fn read, void* context, u64 bytes,
                      const generation_root& root, const u8 (&expected_sdk)[32], generation& output);
error validate_generation(const generation& value);

struct activation_ticket { generation_root root; u64 sequence; u32 index, reserved; };
// A single trusted launcher's volatile registry of preapproved generations.
// No IPC entry point, persistence, signature policy or authority is implied.
class activation_catalog {
public:
    error initialize(const generation_root* roots, u32 count, u32 initial);
    error capture(activation_ticket& ticket) const;
    error admit(const activation_ticket& ticket) const;
    error activate(u32 index, u64 expected_sequence);
    error revoke(u32 index, u64 expected_sequence);
    u64 sequence() const { return sequence_; }
private:
    generation_root roots_[activation_max_generations]{};
    u64 sequence_ = 0;
    u32 count_ = 0, active_ = activation_max_generations, revoked_ = 0;
};
}
