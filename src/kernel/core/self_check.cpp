#include <xos/format.hpp>
#include <xos/memory.hpp>

namespace xos {
namespace {
constexpr u64 check_virtual = 0x40000000ull;
constexpr u64 check_pattern = 0x1122334455667788ull;

void report(const char* result, const char* reason) {
    format::text("[vm] event=self_check result=");
    format::text(result);
    if (reason != nullptr) {
        format::text(" reason=");
        format::text(reason);
    }
    format::text("\r\n");
}
}

bool memory_self_check() {
    u64 physical = 0;
    if (allocate_page(&physical) != memory_result::none) {
        report("fail", "allocate");
        return false;
    }
    const page_permissions permissions{true, false, false};
    if (map_page(check_virtual, physical, permissions) != memory_result::none) {
        (void)release_page(physical);
        report("fail", "map");
        return false;
    }
    auto* word = reinterpret_cast<volatile u64*>(check_virtual);
    *word = check_pattern;
    const bool readback = (*word == check_pattern);

    u64 queried_physical = 0;
    page_permissions queried_permissions{};
    const memory_result query = query_page(check_virtual, &queried_physical, &queried_permissions);
    const memory_result duplicate = map_page(check_virtual, physical, permissions);
    const memory_result unmapped = unmap_page(check_virtual);
    const memory_result released = release_page(physical);

    const bool ok = readback && query == memory_result::none &&
                    queried_physical == physical &&
                    queried_permissions.writable && !queried_permissions.executable &&
                    duplicate == memory_result::already_mapped &&
                    unmapped == memory_result::none && released == memory_result::none;
    if (!ok) {
        report("fail", "mismatch");
        return false;
    }
    format::text("[vm] event=self_check result=pass address=");
    format::hex(check_virtual);
    format::text(" physical=");
    format::hex(physical);
    format::text("\r\n");
    return true;
}
}
