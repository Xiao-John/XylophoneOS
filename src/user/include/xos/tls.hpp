// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/elf.hpp>
namespace xos::sdk {
// ISA backend owns static-TLS layout; generic ELF parsing only validates metadata.
i64 map_static_tls(const elf::load_plan& plan, elf::read_exact_fn read_exact,
                   void* context, u64 child);
}
