// SPDX-License-Identifier: Apache-2.0
// Real grant stores and physical allocator. Linux shared mappings substitute
// page tables; PCI/PIC callbacks below are deterministic hardware boundaries.
#include "core/device_grants.hpp"
#include "core/vm_pin.hpp"
#include <xos/memory.hpp>
#include <cassert>
#include <cstdio>
#include <map>
#include <string>
#include <vector>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

using namespace xos;
namespace {
constexpr u64 ram_begin = 0x10000000, ram_bytes = 0x4000000, mmio_begin = 0xe0000000;
int ram_fd, mmio_fd, map_budget = -1;
u32 scenarios, cancelled;
u64 pinned_pid;
vm_pin pin;
bool stop_ok = true, start_ok = true;
u64 awakened_event;
i64 awakened_result;
device_output awakened_output;
std::map<u64, bool> mappings;
std::vector<std::string> operations;
u64 host_address(u64 pid, u64 address) { return address + pid * 0x100000000ull; }
void release(void*, u64 physical) {
    operations.emplace_back("release");
    assert(release_user_page(physical) == memory_result::none);
}
bool map_page(void*, u64 pid, u64 address, u64 physical, bool write, bool dma) {
    if (map_budget == 0) return false;
    if (map_budget > 0) --map_budget;
    const u64 host = host_address(pid, address);
    const bool ram = physical < max_managed_phys;
    assert(ram == dma);
    if (ram) assert(retain_user_page(physical) == memory_result::none);
    void* result = mmap(reinterpret_cast<void*>(host), 4096, PROT_READ | (write ? PROT_WRITE : 0),
                        MAP_SHARED | MAP_FIXED_NOREPLACE, ram ? ram_fd : mmio_fd,
                        static_cast<off_t>(physical - (ram ? ram_begin : mmio_begin)));
    if (result == MAP_FAILED) { if (ram) release(nullptr, physical); return false; }
    mappings.emplace(host, ram);
    return true;
}
std::map<u64, u64> mapped_physical;
bool map_tracked(void* context, u64 pid, u64 address, u64 physical, bool write, bool dma) {
    if (!map_page(context, pid, address, physical, write, dma)) return false;
    mapped_physical.emplace(host_address(pid, address), physical);
    return true;
}
void unmap(void*, u64 pid, u64 address, bool dma) {
    operations.emplace_back("unmap");
    const u64 host = host_address(pid, address);
    assert(mappings.at(host) == dma);
    assert(munmap(reinterpret_cast<void*>(host), 4096) == 0);
    if (dma) assert(release_user_page(mapped_physical.at(host)) == memory_result::none);
    mapped_physical.erase(host); mappings.erase(host);
}
bool pinned(void*, u64 pid, u64 begin, u64 end) { return pinned_pid == pid && pin.overlaps(begin, end); }
void cancel(void*, u64 pid, u64 begin, u64 end) {
    if (pinned(nullptr, pid, begin, end)) { pin.clear(); ++cancelled; }
}
bool authorized(void*, u64 issuer, u64 target) { return issuer == 1 && target == 2; }
i64 inspect(void*, u64 instance, u64, device_grants::description& out) {
    if (instance != 10 && instance != 11) return device_no_device;
    out = {}; out.bars[0] = {mmio_begin, 0x4000}; out.irq = 11; out.irq_available = true;
    out.configuration[0] = 0x10411af4;
    return 0;
}
bool enable(void*, u64) { return true; }
bool start(void*, u64) { operations.emplace_back("start"); return start_ok; }
bool stop(void*, u64) { operations.emplace_back("stop"); return stop_ok; }
void disable(void*, u64) { operations.emplace_back("disable"); }
bool dma_allocate(void*, u32 pages, u64 alignment, u64& physical) {
    return allocate_contiguous_user_pages(pages, alignment, &physical) == memory_result::none;
}
void mask(void*, u8) { operations.emplace_back("mask"); }
bool unmask(void*, u64, u8) { operations.emplace_back("unmask"); return true; }
void wake(void*, u64 event, i64 result, const device_output& out) {
    awakened_event = event; awakened_result = result; awakened_output = out;
}
device_grants::backend hardware{nullptr, authorized, inspect, enable, start, stop, disable,
    dma_allocate, release, map_tracked, unmap, pinned, cancel, mask, unmask, wake};

void read_only_fault(u64 address) {
    const pid_t child = fork(); assert(child >= 0);
    if (!child) { *reinterpret_cast<volatile u64*>(address) = 7; _exit(99); }
    int status = 0; assert(waitpid(child, &status, 0) == child);
    assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGSEGV);
}
void baseline(u32 free) {
    assert(memory_status().free_pages == free);
    assert(user_pages_status().unique_pages == 0 && user_pages_status().references == 0);
    assert(mappings.empty());
}
void device_cases(u32 free) {
    device_grants::store store;
    device_grant_input input{2, 10, device_right_all, 0};
    device_output grant{}, out{}, mmio{}, dma{}, event{};
    assert(store.grant(hardware, 2, input, grant) == device_denied);
    assert(store.grant(hardware, 1, input, grant) == 0);
    assert(store.grant(hardware, 1, input, out) == device_busy);
    assert(store.query(3, grant.token, 0, out) == device_denied);
    assert(store.query(2, grant.token, 0, out) == 0 && out.length == 0x4000 && out.address == 0);
    assert(store.query(2, grant.token, device_configuration_index, out) == 0 && (out.attributes >> 32) == 0x10411af4);
    ++scenarios;
    assert(store.map(hardware, 2, grant.token, {0, 0, 8192, 3}, mmio) == 0);
    *reinterpret_cast<u64*>(host_address(2, mmio.address)) = 0x12345;
    pinned_pid = 2; assert(pin.set(mmio.address, 8));
    assert(store.unmap(hardware, 2, mmio.token) == device_busy);
    pin.clear(); assert(store.unmap(hardware, 2, mmio.token) == 0);
    assert(store.unmap(hardware, 2, mmio.token) == device_stale); ++scenarios;
    assert(store.dma_allocate(hardware, 2, grant.token, {5000, 65536, device_dma_direction::from_device, 0}, dma) == 0);
    assert(dma.length == 8192 && dma.offset % 65536 == 0 && dma.rights == 1);
    *reinterpret_cast<u64*>(dma.offset) = 0xabcdef;
    assert(*reinterpret_cast<u64*>(host_address(2, dma.address)) == 0xabcdef);
    read_only_fault(host_address(2, dma.address)); ++scenarios;
    assert(store.irq_bind(hardware, 2, grant.token, 6, event) == 0);
    assert(store.irq_wait(2, event.token, 0, out) == device_busy);
    assert(store.interrupt(hardware, 11) && awakened_event == event.token && awakened_output.offset == 1);
    assert(store.irq_wait(2, event.token, 0, out) == 0 && out.offset == 1);
    assert(store.irq_ack(hardware, 3, event.token, 1) == device_denied);
    assert(store.irq_ack(hardware, 2, event.token, 0) == device_stale);
    assert(store.irq_ack(hardware, 2, event.token, 1) == 0);
    assert(store.irq_ack(hardware, 2, event.token, 1) == device_stale);
    assert(store.irq_wait(2, event.token, 0, out) == device_stale); ++scenarios;
    operations.clear(); assert(store.dma_release(hardware, 2, dma.token) == 0);
    assert(operations.size() == 6 && operations[0] == "mask" && operations[1] == "unmap" &&
           operations[2] == "unmap" && operations[3] == "stop" && operations[4] == "release");
    assert(store.close(hardware, 3, grant.token, true) == device_denied);
    assert(store.close(hardware, 1, grant.token, true) == 0 && awakened_result == device_closed);
    baseline(free); ++scenarios;
    assert(store.grant(hardware, 1, input, grant) == 0);
    map_budget = 1;
    assert(store.dma_allocate(hardware, 2, grant.token, {8192, 4096, device_dma_direction::bidirectional, 0}, dma) == device_resources);
    map_budget = -1;
    assert(user_pages_status().unique_pages == 0 && mappings.empty());
    start_ok = false;
    assert(store.dma_allocate(hardware, 2, grant.token, {4096, 4096, device_dma_direction::bidirectional, 0}, dma) == device_io);
    start_ok = true; baseline(free); ++scenarios;
    assert(store.grant(hardware, 1, input, grant) == 0);
    assert(store.map(hardware, 2, grant.token, {0, 0, 4096, 3}, mmio) == 0);
    assert(store.dma_allocate(hardware, 2, grant.token, {4096, 4096, device_dma_direction::bidirectional, 0}, dma) == 0);
    pinned_pid = 2; assert(pin.set(mmio.address, 8));
    store.revoke_process(hardware, 1);
    assert(!pin.active() && cancelled == 1); baseline(free); ++scenarios;
    assert(store.grant(hardware, 1, input, grant) == 0);
    assert(store.dma_allocate(hardware, 2, grant.token, {8192, 4096, device_dma_direction::bidirectional, 0}, dma) == 0);
    stop_ok = false;
    assert(store.dma_release(hardware, 2, dma.token) == device_unknown);
    assert(mappings.empty() && user_pages_status().unique_pages == 2 && user_pages_status().references == 2);
    assert(memory_status().free_pages == free - 2);
    assert(store.grant(hardware, 1, input, out) == device_unknown);
    assert(store.query(2, grant.token, 0, out) == device_stale);
    assert(store.dma_release(hardware, 2, dma.token) == device_stale); ++scenarios;
}
}
int main() {
    ram_fd = memfd_create("xos-grants-ram", 0); mmio_fd = memfd_create("xos-grants-mmio", 0);
    assert(ram_fd >= 0 && mmio_fd >= 0);
    assert(ftruncate(ram_fd, ram_bytes) == 0 && ftruncate(mmio_fd, 0x4000) == 0);
    assert(mmap(reinterpret_cast<void*>(ram_begin), ram_bytes, PROT_READ | PROT_WRITE,
                MAP_SHARED | MAP_FIXED_NOREPLACE, ram_fd, 0) != MAP_FAILED);
    boot_info info{}; info.reserved_low_end = ram_begin; info.region_count = 1;
    memory_region region{}; region.base = ram_begin; region.length = ram_bytes; region.kind = memory_kind::usable;
    memory_init(info, &region);
    const u32 free = memory_status().free_pages;
    device_cases(free);
    printf("IPC_DEVICE_IMPLEMENTATION_SCENARIOS_PASSED=%u\n", scenarios);
}
