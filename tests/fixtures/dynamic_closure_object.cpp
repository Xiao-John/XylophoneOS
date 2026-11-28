// SPDX-License-Identifier: Apache-2.0
#include <xos/dynamic_abi.hpp>
#ifndef FIXTURE_ROLE
#error FIXTURE_ROLE is required
#endif
using namespace xos;
using namespace xos::dynamic;
struct [[gnu::packed]] note_record { u32 namesz, descsz, type; char name[4]; object_identity identity; };
[[gnu::section(".note.xos"), gnu::aligned(4), gnu::used]] const note_record fixture_note{
    4, sizeof(object_identity), identity_note_type, {'X', 'O', 'S', 0},
    {identity_magic, identity_version, sizeof(object_identity), static_cast<object_role>(FIXTURE_ROLE),
     62, 1, 1, 1, 1, 2, profile_glibc_v1, cpu_x86_64_baseline, {0xa1}, {}}};
#if FIXTURE_ROLE == 4
extern "C" { thread_local int fixture_tls = 9; }
extern "C" int fixture_value() { return fixture_tls; }
#elif FIXTURE_ROLE == 3
extern "C" int fixture_value();
// These ELF parser fixtures are never executed. Resolve the library's actual
// GD TLS call without importing a host or target libc into its dependency graph.
extern "C" void* __tls_get_addr(const void*) { return nullptr; }
extern "C" int _start() { return fixture_value(); }
#else
extern "C" int _start() { return FIXTURE_ROLE; }
#endif
