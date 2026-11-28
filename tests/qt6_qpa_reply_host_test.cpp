// SPDX-License-Identifier: Apache-2.0
#include "../src/ports/qt6/qpa/interactium_reply.hpp"
#include "../src/user/interactium/dispatcher.hpp"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <vector>

using namespace xos;
using namespace xos::interactium;

namespace {
unsigned cases = 0;
void require(bool condition, const char* name) {
    if (!condition) { std::fprintf(stderr, "FAIL qpa reply %s\n", name); std::exit(1); }
}
void passed(const char* name) {
    ++cases;
    std::printf("PASS qpa reply case=%s\n", name);
}
struct sample {
    wire_header request{};
    std::vector<u8> response;
    wire_header header() const {
        wire_header result{};
        std::memcpy(&result, response.data(), sizeof(result));
        return result;
    }
    void header(const wire_header& value) { std::memcpy(response.data(), &value, sizeof(value)); }
};
struct server {
    service model;
    protocol_dispatcher dispatcher{model, 37};
    u64 sequence = 0;
    sample exchange(message_type type, u64 object, const void* payload = nullptr, u32 length = 0) {
        sample result;
        result.request = {protocol_version, u32(sizeof(wire_header)) + length, type, 0,
                          ++sequence, dispatcher.session().value, object, length, 0};
        std::vector<u8> request(result.request.size);
        std::memcpy(request.data(), &result.request, sizeof(result.request));
        if (length) std::memcpy(request.data() + sizeof(result.request), payload, length);
        result.response.resize(process_pipe_bytes);
        u32 received = 0;
        require(dispatcher.dispatch(request.data(), u32(request.size()), result.response.data(),
                                    u32(result.response.size()), received) == 0, "real dispatcher reply");
        result.response.resize(received);
        return result;
    }
};
wire_header accepted(const char* name, const sample& source, u32 capacity) {
    auto body = std::make_unique<u8[]>(capacity);
    std::fill_n(body.get(), capacity, u8(0xa5));
    wire_header reply{};
    u32 length = 0;
    require(qt::decode_interactium_reply(source.response.data(), i64(source.response.size()),
                source.request, reply, body.get(), capacity, length) == 0, name);
    const auto original = source.header();
    require(std::memcmp(&reply, &original, sizeof(reply)) == 0 && length == original.payload_length &&
            std::memcmp(body.get(), source.response.data() + sizeof(reply), length) == 0, name);
    require(std::all_of(body.get() + length, body.get() + capacity,
                        [](u8 byte) { return byte == 0xa5; }), name);
    passed(name);
    return reply;
}
void rejected_view(const char* name, const u8* response, i64 received, const wire_header& request,
                   u32 capacity, i64 expected = process_error_invalid, bool null_body = false) {
    // These are actual allocations of the advertised small capacity. ASan's
    // redzone catches any payload copy that runs before the capacity check.
    const u32 allocated = capacity ? capacity : 1;
    auto body = std::make_unique<u8[]>(allocated);
    std::fill_n(body.get(), allocated, u8(0xa5));
    wire_header reply{91, 92, message_type::disconnect, 93, 94, 95, 96, 97, 98};
    const auto before = reply;
    u32 length = 0xabcdef01;
    require(qt::decode_interactium_reply(response, received, request, reply,
                null_body ? nullptr : body.get(), capacity, length) == expected, name);
    require(std::memcmp(&reply, &before, sizeof(reply)) == 0 && length == 0xabcdef01 &&
            std::all_of(body.get(), body.get() + allocated, [](u8 byte) { return byte == 0xa5; }), name);
    passed(name);
}
void rejected(const char* name, const sample& source, u32 capacity) {
    rejected_view(name, source.response.data(), i64(source.response.size()), source.request, capacity);
}
sample resized(sample source, u32 length) {
    auto header = source.header();
    header.payload_length = length;
    header.size = u32(sizeof(header)) + length;
    source.response.resize(header.size, 0x5a);
    source.header(header);
    return source;
}
i64 status(const sample& source) {
    status_payload result{};
    std::memcpy(&result, source.response.data() + sizeof(wire_header), sizeof(result));
    return result.result;
}
} // namespace

int main() {
    server production;
    const hello_payload hello{protocol_version, 0, 800, 600};
    const auto greeting = production.exchange(message_type::hello, 0, &hello, sizeof(hello));
    const auto greeted = accepted("real_hello", greeting, sizeof(hello_reply_payload));
    require(greeted.type == message_type::hello_reply && greeted.session != 0, "real hello session");

    const create_window_payload window{10, 10, 96, 64, window_role::normal, 0, 0};
    const auto created = production.exchange(message_type::create_window, 0, &window, sizeof(window));
    const auto created_header = accepted("real_create_status", created, sizeof(status_payload));
    require(created_header.object != 0 && status(created) == 0, "real window created");
    const auto busy = production.exchange(message_type::input, created_header.object);
    accepted("real_input_busy_status", busy, sizeof(input_payload));
    require(status(busy) == i64(dispatch_result::busy), "real input busy result");

    display_event pointer{};
    pointer.sequence = 1; pointer.kind = 3; pointer.x = 20; pointer.y = 20;
    require(production.model.queue_input(pointer), "real input queued");
    const auto input = production.exchange(message_type::input, created_header.object);
    const auto event_header = accepted("real_input_event", input, sizeof(input_payload));
    require(event_header.type == message_type::input, "real input event type");
    const tile_payload tile{};
    const auto failed_tile = production.exchange(message_type::write_tile, created_header.object, &tile, sizeof(tile));
    accepted("real_write_tile_error_status", failed_tile, sizeof(status_payload));
    require(status(failed_tile) == i64(dispatch_result::malformed), "real error result preserved");

    rejected("status_heap_capacity_7", created, sizeof(status_payload) - 1);
    rejected("hello_heap_capacity_31", greeting, sizeof(hello_reply_payload) - 1);
    rejected("input_heap_capacity_47", input, sizeof(input_payload) - 1);
    rejected("zero_capacity", created, 0);
    const auto long_status = resized(created, sizeof(status_payload) + 1);
    rejected("status_oversize_small_buffer", long_status, sizeof(status_payload));
    rejected("status_oversize_roomy_buffer", long_status, 64);
    rejected("status_short_payload", resized(created, sizeof(status_payload) - 1), sizeof(status_payload));
    rejected("hello_short_payload", resized(greeting, sizeof(hello_reply_payload) - 1), sizeof(hello_reply_payload));
    rejected("hello_oversize_payload", resized(greeting, sizeof(hello_reply_payload) + 1), 64);
    rejected("input_short_payload", resized(input, sizeof(input_payload) - 1), sizeof(input_payload));
    rejected("input_oversize_payload", resized(input, sizeof(input_payload) + 1), 64);
    rejected("full_transport_payload_small_buffer", resized(created, max_wire_payload), sizeof(status_payload));

    // In-object canaries additionally cover stack destinations without relying
    // on an allocator redzone to observe the original small-buffer failure.
    struct guarded_status { std::array<u8, 8> before, body, after; } guarded{};
    std::memset(&guarded, 0xa5, sizeof(guarded));
    const auto original_guard = guarded;
    wire_header guard_reply{};
    u32 guard_length = 0;
    require(qt::decode_interactium_reply(long_status.response.data(), i64(long_status.response.size()),
                created.request, guard_reply, guarded.body.data(), u32(guarded.body.size()), guard_length)
                == process_error_invalid &&
            std::memcmp(&guarded, &original_guard, sizeof(guarded)) == 0, "status stack guard");
    passed("status_stack_canaries");

    auto wrong = resized(created, sizeof(input_payload));
    auto header = wrong.header(); header.type = message_type::input; wrong.header(header);
    rejected("wrong_reply_type_with_room", wrong, sizeof(input_payload));
    wrong = created; wrong.request.type = message_type::hello; wrong.request.session = 0;
    rejected("hello_rejects_status", wrong, sizeof(hello_reply_payload));
    wrong = created; header = wrong.header(); ++header.sequence; wrong.header(header);
    rejected("wrong_sequence", wrong, sizeof(status_payload));
    wrong = created; header = wrong.header(); ++header.session; wrong.header(header);
    rejected("wrong_session", wrong, sizeof(status_payload));
    wrong = created; header = wrong.header(); ++header.version; wrong.header(header);
    rejected("wrong_version", wrong, sizeof(status_payload));
    wrong = created; header = wrong.header(); ++header.size; wrong.header(header);
    rejected("wrong_wire_size", wrong, sizeof(status_payload));
    wrong = created; header = wrong.header(); ++header.payload_length; wrong.header(header);
    rejected("wrong_payload_length", wrong, sizeof(status_payload));
    wrong = created; wrong.response.pop_back();
    rejected("truncated_payload", wrong, sizeof(status_payload));
    const std::array<u8, sizeof(wire_header) - 1> short_header{};
    rejected_view("truncated_header", short_header.data(), i64(short_header.size()), created.request,
                  sizeof(status_payload), process_error_state);
    rejected_view("negative_receive", nullptr, -1, created.request, sizeof(status_payload), process_error_state);
    rejected_view("null_response", nullptr, i64(created.response.size()), created.request, sizeof(status_payload));
    rejected_view("null_destination", created.response.data(), i64(created.response.size()), created.request,
                  sizeof(status_payload), process_error_invalid, true);
    rejected_view("oversize_transport_result", short_header.data(), process_pipe_bytes + 1,
                  created.request, sizeof(status_payload));
    rejected_view("receive_length_no_u32_wrap", short_header.data(), (i64(1) << 32) + i64(created.response.size()),
                  created.request, sizeof(status_payload));
    std::printf("PASS qpa reply total=%u\n", cases);
    return 0;
}
