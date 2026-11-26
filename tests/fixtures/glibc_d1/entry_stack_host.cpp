// SPDX-License-Identifier: Apache-2.0
#include "entry_stack.hpp"
#include <xos/vm_abi.hpp>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <elf.h>
#include <new>
#include <sys/mman.h>
#ifdef D1_NATIVE_GUEST
#include <sys/random.h>
#endif
#ifdef D1_AUXV_CONSUMER
#include <sys/auxv.h>
#endif

using namespace xos;
using namespace xos::glibc_d1;

struct fixture_image {
    elf::segment loads[64];
    mapped_image image;
    main_headers headers;
};

static constexpr u64 fixture_span = 2 * vm_page_size;

static void read_image(const char* path, u64 bias, bool require_phdr, fixture_image& fixture) {
    FILE* file = std::fopen(path, "rb");
    Elf64_Ehdr ehdr;
    assert(file && std::fread(&ehdr, sizeof(ehdr), 1, file) == 1);
    assert(ehdr.e_type == ET_DYN && ehdr.e_machine == EM_X86_64 && ehdr.e_phentsize == sizeof(Elf64_Phdr));
    assert(ehdr.e_phnum > 0 && ehdr.e_phnum <= 64 && std::fseek(file, ehdr.e_phoff, SEEK_SET) == 0);
    fixture.image = {bias, ehdr.e_entry, fixture.loads, 0};
    bool phdr_found = false;
    bool interp_found = false;
    for (u32 i = 0; i < ehdr.e_phnum; ++i) {
        Elf64_Phdr phdr;
        assert(std::fread(&phdr, sizeof(phdr), 1, file) == 1);
        if (phdr.p_type == PT_LOAD) {
            assert(!require_phdr || phdr_found);
            fixture.loads[fixture.image.load_count++] = {phdr.p_offset, phdr.p_vaddr, phdr.p_filesz,
                                                        phdr.p_memsz, phdr.p_flags};
        } else if (phdr.p_type == PT_PHDR) {
            assert(!phdr_found && phdr.p_offset == ehdr.e_phoff && phdr.p_filesz == ehdr.e_phnum * sizeof(phdr));
            fixture.headers = {phdr.p_offset, phdr.p_vaddr, ehdr.e_phnum};
            phdr_found = true;
        } else if (phdr.p_type == PT_DYNAMIC || phdr.p_type == PT_INTERP) {
            assert(!require_phdr || phdr_found);
            if (phdr.p_type == PT_INTERP) { interp_found = true; }
        }
    }
    assert(!require_phdr || (phdr_found && interp_found));
    // Both generated fixtures occupy exactly two pages with one LOAD each.
    auto* base = reinterpret_cast<u8*>(bias);
    assert(fixture.image.load_count == 2);
    assert(mmap(base, fixture_span, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) == base);
    for (u32 page = 0; page < 2; ++page) {
        const auto& load = fixture.loads[page];
        const u64 start = page * vm_page_size;
        assert(load.address >= start && load.address < start + vm_page_size);
        assert(load.file_bytes <= load.memory_bytes && load.memory_bytes <= start + vm_page_size - load.address);
        assert(load.permissions == (page == 0 ? map_read | map_execute : map_read | map_write));
        assert(mprotect(base + start, vm_page_size, PROT_READ | PROT_WRITE) == 0);
        assert(std::fseek(file, load.offset, SEEK_SET) == 0);
        assert(std::fread(base + load.address, 1, load.file_bytes, file) == load.file_bytes);
        assert(mprotect(base + start, vm_page_size, PROT_READ | (page == 0 ? PROT_EXEC : PROT_WRITE)) == 0);
    }
    std::fclose(file);
}

static void unmap_image(const fixture_image& fixture) {
    assert(munmap(reinterpret_cast<void*>(fixture.image.bias), fixture_span) == 0);
}

extern "C" void inspect_entry(const u64* stack);
extern "C" void inspect_entry_words(const u64* stack);
// Exercise the upstream x86-64 stack-entry convention with a local consumer.
// The register holding the host test stack is callee-saved across that call.
asm(".text\n"
    ".globl inspect_entry\n"
    "inspect_entry:\n"
    "push %r12\n"
    "mov %rsp,%r12\n"
    "mov %rdi,%rsp\n"
    "mov %rsp,%rdi\n"
    "call inspect_entry_words\n"
    "mov %r12,%rsp\n"
    "pop %r12\n"
    "ret\n");

static u64 expected_secure;
static u64 expected_environment;
static u32 expected_argc;
static const u64* expected_argv;
static u64 expected_phdr;
static u64 expected_phnum;
static u64 expected_entry;
static u64 expected_base;
static u8* expected_random;
static u8 expected_bytes[16];
static u32 observed;

#ifdef D1_AUXV_CONSUMER
extern "C" {
void _dl_aux_init(Elf64_auxv_t*);
extern Elf64_auxv_t* _dl_auxv;
extern const Elf64_Phdr* _dl_phdr;
extern size_t _dl_phnum, _dl_pagesize;
extern void* _dl_random;
extern int __libc_enable_secure;
}

static void verify_glibc_auxv(const u64* words, const u64* expected) {
    auto* previous_auxv = _dl_auxv;
    auto* previous_random = _dl_random;
    auto previous_secure = __libc_enable_secure;
    auto* vector = reinterpret_cast<Elf64_auxv_t*>(const_cast<u64*>(words));
    _dl_aux_init(vector);
    assert(_dl_auxv == vector);
    assert(reinterpret_cast<u64>(_dl_phdr) == expected_phdr && _dl_phnum == expected_phnum);
    assert(_dl_pagesize == vm_page_size && _dl_random == expected_random);
    assert(__libc_enable_secure == static_cast<int>(expected_secure));
    for (u32 index = 0; expected[index] != AT_NULL; index += 2) {
        assert(getauxval(expected[index]) == expected[index + 1]);
    }
    _dl_aux_init(previous_auxv);
    _dl_random = previous_random;
    __libc_enable_secure = previous_secure;
}
#endif

extern "C" void inspect_entry_words(const u64* stack) {
    assert(reinterpret_cast<u64>(stack) % 16 == 0);
    assert(stack[0] == expected_argc);
    assert(std::memcmp(stack + 1, expected_argv, (expected_argc + 1) * sizeof(u64)) == 0);
    const auto* env = stack + expected_argc + 2;
    assert(*env == expected_environment);
    if (*env != 0) { ++env; }
    assert(*env == 0);
    const u64 expected[] = {AT_PHDR, expected_phdr, AT_PHNUM, expected_phnum, AT_PHENT, sizeof(Elf64_Phdr),
                            AT_ENTRY, expected_entry, AT_BASE, expected_base, AT_PAGESZ, vm_page_size,
                            AT_SECURE, expected_secure, AT_RANDOM, reinterpret_cast<u64>(expected_random), AT_NULL, 0};
    assert(std::memcmp(env + 1, expected, sizeof(expected)) == 0);
#ifdef D1_AUXV_CONSUMER
    verify_glibc_auxv(env + 1, expected);
#endif
    const auto* table = reinterpret_cast<const Elf64_Phdr*>(expected_phdr);
    assert(table[0].p_type == PT_PHDR && table[1].p_type == PT_INTERP);
    const auto* loader_ehdr = reinterpret_cast<const Elf64_Ehdr*>(expected_base);
    assert(loader_ehdr->e_type == ET_DYN);
    assert(std::memcmp(expected_random, expected_bytes, sizeof(expected_bytes)) == 0);
    *expected_random = 0;
    ++observed;
}

static void expect_images(const fixture_image& app, const fixture_image& loader, entry_stack& frame) {
    expected_phdr = app.image.bias + app.headers.address;
    expected_phnum = app.headers.count;
    expected_entry = app.image.bias + app.image.entry;
    expected_base = loader.image.bias;
    expected_random = frame.random;
}

#ifdef D1_NATIVE_GUEST
extern "C" const void* __xos_startup;

static bool native_entropy(u8* bytes, u32 size) {
    if (getrandom(bytes, size, 0) != static_cast<ssize_t>(size)) { return false; }
    std::memcpy(expected_bytes, bytes, size);
    return true;
}

int main(int argc, char** argv) {
    assert(argc == 3);
    fixture_image app, loader;
    read_image(argv[1], 0x100000200000, true, app);
    read_image(argv[2], 0x180040000000, false, loader);
    const auto* startup = static_cast<const startup_info*>(__xos_startup);
    assert(startup->version == 2 && startup->argc == 3);
    const auto* extension = reinterpret_cast<const startup_extension*>(process_startup_begin + startup_extension_offset);
    assert(extension->environment_count == 1);
    expected_environment = *reinterpret_cast<const u64*>(extension->environment);
    assert(std::strncmp(reinterpret_cast<const char*>(expected_environment), "PATH=", 5) == 0);
    expected_argc = startup->argc;
    expected_argv = reinterpret_cast<const u64*>(startup->argv);
    auto& frame = *new (reinterpret_cast<void*>(process_stack_bottom + 16 * vm_page_size)) entry_stack;
    expect_images(app, loader, frame);
    assert(build_entry_stack(startup, app.image, app.headers, loader.image, execution_mode::ordinary,
                             native_entropy, frame));
    inspect_entry(frame.words);
    assert(observed == 1);
#ifdef D1_AUXV_CONSUMER
    expected_secure = 1;
    assert(build_entry_stack(startup, app.image, app.headers, loader.image, execution_mode::secure,
                             native_entropy, frame));
    inspect_entry(frame.words);
    assert(observed == 2);
    std::puts("D1_GLIBC_AUXV_PASS native_decoder=static ordinary=ok secure=ok");
#endif
    unmap_image(loader);
    unmap_image(app);
    std::puts("D1_ENTRY_STACK_GUEST_PASS native_startup=v2 native_entropy=ok private_rsp=ok");
}
#else
static u32 entropy_calls;

static bool fixture_entropy(u8* bytes, u32 size) {
    assert(size == 16);
    for (u8 i = 0; i < size; ++i) { expected_bytes[i] = bytes[i] = i + 11; }
    ++entropy_calls;
    return true;
}

static bool failed_entropy(u8* bytes, u32 size) {
    fixture_entropy(bytes, size);
    return false;
}

int main(int argc, char** argv) {
    assert(argc == 3);
    fixture_image app, loader;
    read_image(argv[1], 0x100000200000, true, app);
    read_image(argv[2], 0x180040000000, false, loader);
    void* region = mmap(reinterpret_cast<void*>(process_stack_bottom), process_stack_top - process_stack_bottom,
                        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    assert(region == reinterpret_cast<void*>(process_stack_bottom));
    auto& frame = *new (reinterpret_cast<void*>(process_startup_begin - sizeof(entry_stack))) entry_stack;
    auto* startup = reinterpret_cast<startup_info*>(process_startup_begin);
    *startup = {startup_magic, 1, sizeof(*startup), 1, 3, process_startup_begin + 256, {0, 1, 2}, 0};
    auto* extension = reinterpret_cast<startup_extension*>(process_startup_begin + startup_extension_offset);
    *extension = {startup_extension_magic, 1, 0, process_startup_begin + 272, 0, {}, {}, {}, 0};
    auto* args = reinterpret_cast<u64*>(startup->argv);
    auto* env = reinterpret_cast<u64*>(extension->environment);
    args[0] = process_startup_begin + 288;
    env[0] = process_startup_begin + 304;
    std::strcpy(reinterpret_cast<char*>(args[0]), "test-pie");
    auto* variable = reinterpret_cast<char*>(env[0]);
    std::strcpy(variable, "APP_SETTING=1");

    const auto build = [&](execution_mode mode = execution_mode::ordinary, entropy_source fill = fixture_entropy) {
        return build_entry_stack(startup, app.image, app.headers, loader.image, mode, fill, frame);
    };
    expected_argc = startup->argc;
    expected_argv = args;
    expect_images(app, loader, frame);
    assert(build());
    inspect_entry(frame.words);
    startup->version = 2;
    startup->reserved = startup_extension_offset;
    expected_environment = env[0];
    expected_secure = 1;
    assert(build(execution_mode::secure));
    inspect_entry(frame.words);
    startup->version = 3;
    expected_secure = 0;
    assert(build());
    inspect_entry(frame.words);
    assert(observed == 3 && entropy_calls == 3);

    startup->argc = process_max_args;
    extension->environment_count = startup_environment_max;
    const auto saved_argv = startup->argv;
    const auto saved_environment = extension->environment;
    startup->argv = process_startup_begin + 0x600;
    extension->environment = process_startup_begin + 0x900;
    auto* maximum_argv = reinterpret_cast<u64*>(startup->argv);
    auto* maximum_env = reinterpret_cast<u64*>(extension->environment);
    for (u32 i = 0; i < process_max_args; ++i) { maximum_argv[i] = args[0]; }
    for (u32 i = 0; i < startup_environment_max; ++i) { maximum_env[i] = env[0]; }
    assert(build());
    assert(frame.words[0] == process_max_args && frame.words[process_max_args + 1] == 0);
    assert(frame.words[process_max_args + startup_environment_max + 2] == 0);
    assert(frame.words[entry_stack_max_words - 2] == AT_NULL && frame.words[entry_stack_max_words - 1] == 0);
    startup->argc = 1;
    startup->argv = saved_argv;
    extension->environment_count = 1;
    extension->environment = saved_environment;

    entry_stack old;
    std::memcpy(&old, &frame, sizeof(frame));
    const auto deny = [&] {
        assert(!build());
        assert(entropy_calls == 4 && std::memcmp(&old, &frame, sizeof(frame)) == 0);
    };
    const char* blocked[] = {"LD_PROFILE=lib", "LD_PRELOAD=file", "GLIBC_TUNABLES=bad"};
    for (const char* name : blocked) {
        std::strcpy(variable, name);
        deny();
    }
    std::strcpy(variable, "APP_SETTING=1");
    env[1] = args[0];
    deny();
    env[1] = 0;
    env[0] = process_stack_top - 1;
    *reinterpret_cast<char*>(env[0]) = 'x';
    deny();
    env[0] = reinterpret_cast<u64>(variable);
    startup->argc = process_max_args + 1;
    deny();
    startup->argc = 1;
    auto header_count = app.headers.count;
    app.headers.count = 65;
    deny();
    app.headers.count = header_count;
    app.headers.file_offset += 8;
    deny();
    app.headers.file_offset -= 8;
    auto bias = loader.image.bias;
    loader.image.bias = app.image.bias;
    deny();
    loader.image.bias = bias;
    auto loader_entry = loader.image.entry;
    loader.image.entry = UINT64_MAX;
    deny();
    loader.image.entry = loader_entry;
    assert(!build(execution_mode::ordinary, failed_entropy));
    assert(entropy_calls == 5 && std::memcmp(&old, &frame, sizeof(frame)) == 0);
    assert(munmap(region, process_stack_top - process_stack_bottom) == 0);
    unmap_image(loader);
    unmap_image(app);
    std::puts("D1_ENTRY_STACK_PASS native_vectors=3 private_rsp=3 maximum=64+64 refusals=11");
}
#endif
