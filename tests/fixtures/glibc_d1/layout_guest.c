// SPDX-License-Identifier: Apache-2.0
#define _GNU_SOURCE 1
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>

struct load_segment {
    size_t file_offset, address, file_size, memory_size, page_start, page_size;
    int final_protection;
};

#include "layout_fixture.h"

static const uintptr_t biases[] = {UINT64_C(0x100000200000), UINT64_C(0x180040000000)};
static const int reserve_flags = MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE;

static int fail(const char *operation)
{
    printf("D1_LAYOUT_FAIL %s errno=%d\n", operation, errno);
    return 1;
}

static int map_fixture(uintptr_t bias)
{
    void *region = mmap((void *)bias, image_span, PROT_NONE, reserve_flags, -1, 0);
    if (region == MAP_FAILED)
        return -1;
    if ((uintptr_t)region != bias) {
        munmap(region, image_span);
        return -1;
    }

    for (size_t i = 0; i < sizeof(loads) / sizeof(loads[0]); ++i) {
        const struct load_segment *load = &loads[i];
        if (mprotect((void *)(bias + load->page_start), load->page_size, PROT_READ | PROT_WRITE) != 0)
            goto failed;
        memcpy((void *)(bias + load->address), image + load->file_offset, load->file_size);
        for (size_t offset = load->file_size; offset < load->memory_size; ++offset) {
            if (*(const unsigned char *)(bias + load->address + offset) != 0)
                goto failed;
        }
    }

    // The embedded fixture has exactly one in-object relative data relocation.
    *(uintptr_t *)(bias + relocation_site) = bias + relocated_data;

    for (size_t i = 0; i < sizeof(loads) / sizeof(loads[0]); ++i) {
        const struct load_segment *load = &loads[i];
        if (mprotect((void *)(bias + load->page_start), load->page_size, load->final_protection) != 0)
            goto failed;
    }
    if (mprotect((void *)(bias + relro_start), relro_size, PROT_READ) != 0)
        goto failed;
    return 0;

failed:
    munmap(region, image_span);
    return -1;
}

static uint64_t run_entry(uintptr_t bias)
{
    uint64_t (*entry)(uint64_t) = (uint64_t (*)(uint64_t))(bias + entry_offset);
    return entry(1023);
}

static int fail_page_access(const char *mode, uintptr_t bias)
{
    uintptr_t address;
    if (strcmp(mode, "relro-write") == 0)
        address = bias + relocation_site;
    else if (strcmp(mode, "rw-exec") == 0)
        address = bias + relocated_data;
    else if (strcmp(mode, "hole-read") == 0)
        address = bias + hole_offset;
    else
        return fail("unknown_mode");

    printf("D1_EXPECT_FAULT %s %llx\n", mode, (unsigned long long)address);
    if (fflush(stdout) != 0)
        return fail("flush_fault_marker");

    if (strcmp(mode, "relro-write") == 0)
        *(volatile uintptr_t *)address = 0;
    else if (strcmp(mode, "rw-exec") == 0) {
        void (*entry)(void) = (void (*)(void))address;
        entry();
    } else
        (void)*(volatile unsigned char *)address;
    return fail("protected_access_returned");
}

int main(int argc, char **argv)
{
    if (map_fixture(biases[0]) != 0)
        return fail("map_first");
    if (argc == 2)
        return fail_page_access(argv[1], biases[0]);
    if (argc != 1 || map_fixture(biases[1]) != 0)
        return fail("map_second");

    errno = 0;
    if (mmap((void *)biases[0], image_span, PROT_NONE, reserve_flags, -1, 0) != MAP_FAILED || errno != EEXIST)
        return fail("exact_collision");

    for (size_t i = 0; i < sizeof(biases) / sizeof(biases[0]); ++i) {
        uintptr_t bias = biases[i];
        uintptr_t pointer = *(const uintptr_t *)(bias + relocation_site);
        if (pointer != bias + relocated_data || *(const uint64_t *)pointer != 0x4090)
            return fail("relocated_data");
        uint64_t first = run_entry(bias);
        uint64_t second = run_entry(bias);
        if (first != 0x448f || second != 0x4c8d || *(const uint64_t *)pointer != second)
            return fail("entry_and_bss");
        printf("D1_LAYOUT %llx %llx %llx %llx\n", (unsigned long long)bias, (unsigned long long)pointer,
               (unsigned long long)first, (unsigned long long)second);
    }

    for (size_t i = 0; i < sizeof(biases) / sizeof(biases[0]); ++i) {
        void *address = (void *)biases[i];
        if (munmap(address, image_span) != 0 ||
            mmap(address, image_span, PROT_NONE, reserve_flags, -1, 0) != address ||
            munmap(address, image_span) != 0)
            return fail("release_and_reuse");
    }
    puts("D1_LAYOUT_PASS collision=EEXIST bss=zero relro=read-only reuse=ok");
    return 0;
}
