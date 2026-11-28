// SPDX-License-Identifier: Apache-2.0
// Production PCI observer with hardware PIO and page-table boundaries replaced.
#include <xos/device_backend.hpp>
#include <xos/memory.hpp>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <sys/mman.h>

using namespace xos;
namespace {
u32 config[64]{};
u32 selected = 0;
u64 mapped_address = 0, mapped_physical = 0;
u32 maps = 0, unmaps = 0;
bool fail_map = false, fail_unmap = false;
constexpr u64 instance = 41;
void device(u32 base) {
    std::memset(config, 0, sizeof(config));
    config[0] = 0x10411af4;
    config[1] = 1u << 20;
    config[2] = 0x02000000;
    config[4] = base;
    config[0x34 / 4] = 0x40;
    config[0x3c / 4] = 0x010a;
    config[0x40 / 4] = 9 | (16u << 16) | (1u << 24);
    config[0x4c / 4] = 56;
}
bool target() { return (selected & 0xffffff00u) == 0x80002800u; }
}

namespace xos::arch {
void out_dword(u16 port, u32 value) {
    if (port == 0xcf8) { selected = value; return; }
    assert(port == 0xcfc);
    if (target()) config[(selected & 255) / 4] = value;
}
u32 in_dword(u16 port) {
    assert(port == 0xcfc);
    if (!target()) return ~u32{0};
    const u32 offset = selected & 255, value = config[offset / 4];
    if (offset >= 16 && offset <= 36 && value == ~u32{0})
        return offset == 16 ? 0xfffff000u : 0;
    return value;
}
void out_word(u16 port, u16 value) {
    assert(port == 0xcfc || port == 0xcfe);
    if (!target()) return;
    auto& current = config[(selected & 255) / 4];
    const u32 shift = (port - 0xcfc) * 8;
    current = (current & ~(0xffffu << shift)) | (u32{value} << shift);
}
}
namespace xos {
memory_result map_pci_device_page(u64 address, u64 physical) {
    if (fail_map) return memory_result::out_of_memory;
    assert(!mapped_address && address >= 0x32000000 && address < 0x33000000);
    void* page = mmap(reinterpret_cast<void*>(address), page_size, PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    assert(page == reinterpret_cast<void*>(address));
    mapped_address = address; mapped_physical = physical; ++maps;
    return memory_result::none;
}
memory_result unmap_page(u64 address) {
    assert(address == mapped_address);
    if (fail_unmap) return memory_result::invalid;
    assert(munmap(reinterpret_cast<void*>(address), page_size) == 0);
    mapped_address = mapped_physical = 0; ++unmaps;
    return memory_result::none;
}
}
namespace xos::platform { void irq_unmask(u8) {} }

int main() {
    device_grants::description result{};
    device(0xe0000000);
    assert(platform::device_inspect(instance, device_right_all, result) == 0);
    assert(maps == 1 && mapped_physical == 0xe0000000 && platform::device_dma_stop(instance));
    assert(platform::device_inspect(instance, device_right_all, result) == device_no_device);
    platform::device_disable(instance);
    assert(unmaps == 1 && !mapped_address && !platform::device_dma_stop(instance));

    // A new function at the same BDF has different BAR resources. It must
    // perform a new map, and its reset byte must govern DMA-stop observation.
    device(0xe1000000);
    assert(platform::device_inspect(instance, device_right_all, result) == 0);
    assert(maps == 2 && mapped_physical == 0xe1000000);
    auto* status = reinterpret_cast<volatile u8*>(mapped_address + 20);
    *status = 1;
    assert(!platform::device_dma_stop(instance));
    *status = 0;
    assert(platform::device_dma_stop(instance));
    fail_unmap = true; platform::device_disable(instance);
    device(0xe2000000);
    assert(platform::device_inspect(instance, device_right_all, result) == device_no_device && maps == 2);
    fail_unmap = false; platform::device_disable(instance);
    assert(unmaps == 2 && !mapped_address);

    // Rejected new resources and failed mapping cannot establish an observer.
    device(0);
    assert(platform::device_inspect(instance, device_right_all, result) == device_no_device && maps == 2);
    device(0xe2000000); fail_map = true;
    assert(platform::device_inspect(instance, device_right_all, result) == device_no_device && maps == 2);
    fail_map = false;
    assert(platform::device_inspect(instance, device_right_all, result) == 0 && maps == 3);
    platform::device_disable(instance);
    assert(unmaps == 3 && !mapped_address);
    std::puts("PCI_OBSERVER_FRESH_MAPPING_PASS");
}
