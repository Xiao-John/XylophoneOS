// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/device_backend.hpp>

namespace xos::device_grants {
struct backend {
    void* context;
    bool (*authorized)(void*, u64 issuer, u64 target);
    i64 (*inspect)(void*, u64 instance, u64 rights, description&);
    bool (*memory_enable)(void*, u64 instance);
    bool (*dma_start)(void*, u64 instance);
    bool (*dma_stop)(void*, u64 instance);
    void (*disable)(void*, u64 instance);
    bool (*allocate)(void*, u32 pages, u64 alignment, u64& physical);
    void (*release)(void*, u64 physical);
    bool (*map)(void*, u64 pid, u64 address, u64 physical, bool write, bool dma);
    void (*unmap)(void*, u64 pid, u64 address, bool dma);
    bool (*pinned)(void*, u64 pid, u64 begin, u64 end);
    void (*cancel_pins)(void*, u64 pid, u64 begin, u64 end);
    void (*irq_mask)(void*, u8 irq);
    bool (*irq_unmask)(void*, u64 instance, u8 irq);
    void (*wake)(void*, u64 event, i64 result, const device_output&);
};

class store {
public:
    i64 grant(backend& io, u64 issuer, const device_grant_input& input, device_output& out) {
        out = {};
        if (!input.rights || (input.rights & ~device_right_all) || input.reserved ||
            !input.device_instance || input.device_instance > 65536 || !input.process_object) return device_invalid;
        if (!io.authorized(io.context, issuer, input.process_object)) return device_denied;
        grant_record* target = nullptr;
        for (auto& item : grants_) {
            if (item.used && item.instance == input.device_instance) return item.quarantined ? device_unknown : device_busy;
            if (!item.used && !target) target = &item;
        }
        if (!target || !next_token_) return device_resources;
        description resources{};
        const i64 result = io.inspect(io.context, input.device_instance, input.rights, resources);
        if (result) return result;
        *target = {};
        target->used = true; target->issuer = issuer; target->owner = input.process_object;
        target->instance = input.device_instance; target->rights = input.rights;
        target->token = target->generation = next_token_++; target->resources = resources;
        out.token = target->token; out.generation = target->generation; out.rights = target->rights;
        return 0;
    }

    i64 query(u64 pid, u64 token, u64 index, device_output& out) {
        out = {}; grant_record* grant = nullptr;
        if (index > 6 && (index < device_configuration_index || index >= device_configuration_index + 64)) return device_invalid;
        const i64 error = owned_grant(pid, token, device_right_query, grant);
        if (error) return error;
        if (index >= device_configuration_index && index < device_configuration_index + 64) {
            out.token = token; out.generation = grant->generation; out.length = 4;
            out.offset = (index - device_configuration_index) * 4;
            out.attributes = device_attribute_configuration |
                (u64{grant->resources.configuration[index - device_configuration_index]} << 32);
            return 0;
        }
        out.token = token; out.generation = grant->generation; out.offset = index;
        if (index == 6 && grant->resources.irq_available) {
            out.attributes = device_attribute_irq; out.length = 1;
        } else if (index < 6 && grant->resources.bars[index].length) {
            out.length = grant->resources.bars[index].length;
            out.rights = device_memory_read | device_memory_write;
            out.attributes = device_attribute_mmio | device_attribute_uncached;
        } else { out = {}; return device_no_device; }
        return 0;
    }

    i64 map(backend& io, u64 pid, u64 token, const device_map_input& input, device_output& out) {
        out = {};
        if (input.index >= 6 || !input.length || input.length > device_mapping_slot_bytes ||
            (input.offset & 4095) || (input.length & 4095) ||
            (input.permissions != 1 && input.permissions != 3)) return device_invalid;
        grant_record* grant = nullptr;
        i64 result = owned_grant(pid, token, device_right_mmio, grant);
        if (result) return result;
        const auto& resource = grant->resources.bars[input.index];
        if (!resource.length) return device_no_device;
        if (input.offset > resource.length || input.length > resource.length - input.offset) return device_invalid;
        mapping_record* target = nullptr; u32 window = 0;
        if (!mapping_slot(pid, target, window) || !next_token_) return device_resources;
        if (!io.memory_enable(io.context, grant->instance)) return device_io;
        result = install(io, *target, *grant, window, resource.physical + input.offset,
                         input.length, input.permissions == 3, false);
        if (result) return result;
        out.token = target->token; out.generation = grant->generation;
        out.address = mapping_address(*target); out.length = input.length; out.rights = input.permissions;
        out.attributes = device_attribute_mmio | device_attribute_uncached;
        return 0;
    }

    i64 unmap(backend& io, u64 pid, u64 token) {
        mapping_record* mapping = nullptr;
        const i64 result = owned_mapping(pid, token, false, mapping);
        if (result) return result;
        const u64 base = mapping_address(*mapping);
        if (io.pinned(io.context, pid, base, base + mapping->length)) return device_busy;
        remove_mapping(io, *mapping, false); *mapping = {};
        return 0;
    }

    i64 dma_allocate(backend& io, u64 pid, u64 token, const device_dma_input& input, device_output& out) {
        out = {};
        const u64 direction = static_cast<u64>(input.direction);
        if (!input.length || input.length > u64{device_dma_max_pages} * 4096 || input.reserved ||
            input.alignment < 4096 || input.alignment > device_mapping_slot_bytes ||
            (input.alignment & (input.alignment - 1)) || direction < 1 || direction > 3) return device_invalid;
        grant_record* grant = nullptr;
        i64 result = owned_grant(pid, token, device_right_dma, grant);
        if (result) return result;
        const u32 pages = static_cast<u32>((input.length + 4095) / 4096);
        u32 owned = 0, owner_pages = 0, total = 0;
        for (const auto& item : mappings_) if (item.used && item.dma) {
            total += static_cast<u32>(item.length / 4096);
            if (item.owner == pid) owner_pages += static_cast<u32>(item.length / 4096);
            if (item.grant == static_cast<u32>(grant - grants_)) owned += static_cast<u32>(item.length / 4096);
        }
        mapping_record* target = nullptr; u32 window = 0;
        if (pages > device_dma_max_pages - owned || pages > device_dma_owner_pages - owner_pages ||
            pages > device_dma_system_pages - total ||
            !mapping_slot(pid, target, window) || !next_token_) return device_resources;
        u64 physical = 0;
        if (!io.allocate(io.context, pages, input.alignment, physical)) return device_resources;
        // from_device is CPU read-only; drivers receive the DMA address only here.
        result = install(io, *target, *grant, window, physical, u64{pages} * 4096, direction != 2, true);
        if (result) {
            for (u32 page = 0; page < pages; ++page) io.release(io.context, physical + u64{page} * 4096);
            return result;
        }
        grant->dma_active = true;
        if (!io.dma_start(io.context, grant->instance)) {
            const i64 stopped = terminate(io, *grant);
            return stopped ? stopped : device_io;
        }
        grant->paused = false;
        if (grant->event && !grant->pending && !grant->overflow &&
            !io.irq_unmask(io.context, grant->instance, grant->resources.irq)) {
            const i64 stopped = terminate(io, *grant);
            return stopped ? stopped : device_io;
        }
        out.token = target->token; out.generation = grant->generation; out.length = target->length;
        out.address = mapping_address(*target); out.offset = physical; out.attributes = direction;
        out.rights = direction == 2 ? device_memory_read : device_memory_read | device_memory_write;
        return 0;
    }

    i64 dma_release(backend& io, u64 pid, u64 token) {
        mapping_record* mapping = nullptr;
        const i64 result = owned_mapping(pid, token, true, mapping);
        if (result) return result;
        auto& grant = grants_[mapping->grant];
        const u64 base = mapping_address(*mapping);
        if (io.pinned(io.context, pid, base, base + mapping->length)) return device_busy;
        if (grant.event) io.irq_mask(io.context, grant.resources.irq);
        remove_mapping(io, *mapping, false);
        if (grant.dma_active && !io.dma_stop(io.context, grant.instance)) return terminate(io, grant, true);
        grant.dma_active = false; grant.paused = true;
        release_pages(io, *mapping); *mapping = {};
        return 0;
    }

    i64 irq_bind(backend& io, u64 pid, u64 token, u64 index, device_output& out) {
        out = {};
        if (index != 6) return device_invalid;
        grant_record* grant = nullptr;
        const i64 result = owned_grant(pid, token, device_right_irq, grant);
        if (result) return result;
        if (!grant->resources.irq_available) return device_no_device;
        if (grant->event) return device_busy;
        for (const auto& item : grants_)
            if (item.used && item.event && item.resources.irq == grant->resources.irq) return device_busy;
        if (!next_token_) return device_resources;
        grant->event = next_token_++;
        if (!grant->paused && !io.irq_unmask(io.context, grant->instance, grant->resources.irq)) {
            grant->event = 0; return device_io;
        }
        event_output(*grant, out);
        return 0;
    }

    i64 irq_wait(u64 pid, u64 token, u64 acknowledged, device_output& out) {
        out = {}; grant_record* grant = nullptr;
        const i64 result = owned_event(pid, token, grant);
        if (result) return result;
        if (grant->overflow) return device_io;
        if (acknowledged != grant->acknowledged) return device_stale;
        if (!grant->pending) return device_busy;
        event_output(*grant, out); return 0;
    }

    i64 irq_ack(backend& io, u64 pid, u64 token, u64 sequence) {
        grant_record* grant = nullptr;
        const i64 result = owned_event(pid, token, grant);
        if (result) return result;
        if (grant->overflow) return device_io;
        if (!grant->pending || sequence != grant->sequence) return device_stale;
        if (!grant->paused && !io.irq_unmask(io.context, grant->instance, grant->resources.irq)) return device_io;
        grant->acknowledged = sequence; grant->pending = false;
        return 0;
    }

    bool interrupt(backend& io, u8 irq) {
        for (auto& grant : grants_) {
            if (!grant.used || !grant.event || grant.resources.irq != irq) continue;
            io.irq_mask(io.context, irq);
            // One masked outstanding level; duplicate arrivals coalesce until ACK.
            if (!grant.pending) {
                if (grant.sequence == ~u64{0}) grant.overflow = true;
                else { ++grant.sequence; grant.pending = true; }
            }
            device_output out{};
            if (!grant.overflow) event_output(grant, out);
            io.wake(io.context, grant.event, grant.overflow ? device_io : 0, out);
            return true;
        }
        return false;
    }

    i64 close(backend& io, u64 pid, u64 token, bool revoke) {
        for (auto& grant : grants_) if (grant.used && grant.token == token && token) {
            if ((revoke ? grant.issuer : grant.owner) != pid) return device_denied;
            return terminate(io, grant);
        }
        return device_stale;
    }
    void revoke_process(backend& io, u64 pid) {
        for (auto& grant : grants_) if (grant.used && !grant.quarantined &&
            (grant.owner == pid || grant.issuer == pid)) (void)terminate(io, grant);
    }
    bool mapped(u64 pid) const {
        for (const auto& item : mappings_) if (item.used && item.mapped && item.owner == pid) return true;
        return false;
    }

private:
    struct grant_record {
        bool used, closing, quarantined, dma_active, paused, pending, overflow;
        u64 token, generation, issuer, owner, instance, rights, event, sequence, acknowledged;
        description resources;
    };
    struct mapping_record {
        bool used, mapped, dma;
        u64 token, owner, physical, length;
        u32 grant, window;
    };
    grant_record grants_[device_max_grants]{};
    mapping_record mappings_[8 * device_mapping_slots]{};
    u64 next_token_ = 1;
    i64 owned_grant(u64 pid, u64 token, u64 rights, grant_record*& out) {
        for (auto& item : grants_) if (item.used && token && item.token == token) {
            if (item.owner != pid || (rights & ~item.rights)) return device_denied;
            if (item.closing) return device_closed;
            out = &item; return 0;
        }
        return device_stale;
    }
    i64 owned_mapping(u64 pid, u64 token, bool dma, mapping_record*& out) {
        for (auto& item : mappings_) if (item.used && token && item.token == token) {
            if (item.owner != pid) return device_denied;
            if (item.dma != dma) return device_invalid;
            out = &item; return 0;
        }
        return device_stale;
    }
    i64 owned_event(u64 pid, u64 token, grant_record*& out) {
        for (auto& item : grants_) if (item.used && token && item.event == token) {
            if (item.owner != pid) return device_denied;
            out = &item; return 0;
        }
        return device_stale;
    }
    bool mapping_slot(u64 pid, mapping_record*& target, u32& window) {
        bool occupied[device_mapping_slots]{};
        for (auto& item : mappings_) {
            if (!item.used && !target) target = &item;
            if (item.used && item.mapped && item.owner == pid) occupied[item.window] = true;
        }
        window = 0;
        while (window < device_mapping_slots && occupied[window]) ++window;
        return target && window < device_mapping_slots;
    }
    static u64 mapping_address(const mapping_record& mapping) {
        return device_window_begin + u64{mapping.window} * device_mapping_slot_bytes;
    }
    static void event_output(const grant_record& grant, device_output& out) {
        out = {}; out.token = grant.event; out.generation = grant.generation;
        out.offset = grant.sequence; out.attributes = device_attribute_irq;
    }
    i64 install(backend& io, mapping_record& target, grant_record& grant, u32 window,
                u64 physical, u64 length, bool write, bool dma) {
        const u64 base = device_window_begin + u64{window} * device_mapping_slot_bytes;
        u64 mapped = 0;
        for (; mapped < length; mapped += 4096)
            if (!io.map(io.context, grant.owner, base + mapped, physical + mapped, write, dma)) break;
        if (mapped != length) {
            while (mapped) { mapped -= 4096; io.unmap(io.context, grant.owner, base + mapped, dma); }
            return device_resources;
        }
        target = {true, true, dma, next_token_++, grant.owner, physical, length,
                  static_cast<u32>(&grant - grants_), window};
        return 0;
    }
    static void remove_mapping(backend& io, mapping_record& item, bool cancel) {
        if (!item.mapped) return;
        const u64 base = mapping_address(item);
        if (cancel) io.cancel_pins(io.context, item.owner, base, base + item.length);
        for (u64 offset = 0; offset < item.length; offset += 4096)
            io.unmap(io.context, item.owner, base + offset, item.dma);
        item.mapped = false; item.token = 0;
    }
    static void release_pages(backend& io, const mapping_record& item) {
        if (item.dma) for (u64 offset = 0; offset < item.length; offset += 4096)
            io.release(io.context, item.physical + offset);
    }
    i64 terminate(backend& io, grant_record& grant, bool unknown = false) {
        grant.closing = true;
        const u64 event = grant.event;
        grant.token = grant.event = 0;
        if (event) { io.irq_mask(io.context, grant.resources.irq); io.wake(io.context, event, device_closed, {}); }
        const u32 slot = static_cast<u32>(&grant - grants_);
        for (auto& item : mappings_) if (item.used && item.grant == slot) remove_mapping(io, item, true);
        const bool stopped = !unknown && (!grant.dma_active || io.dma_stop(io.context, grant.instance));
        io.disable(io.context, grant.instance);
        for (auto& item : mappings_) if (item.used && item.grant == slot) {
            if (!stopped && item.dma) continue;
            release_pages(io, item); item = {};
        }
        if (!stopped) { grant.quarantined = true; return device_unknown; }
        grant = {}; return 0;
    }
};
}
