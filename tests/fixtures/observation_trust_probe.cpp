// SPDX-License-Identifier: Apache-2.0
#include "observation.hpp"
#include "observation_trust_data.hpp"
#include <psa/crypto.h>
#include <stdio.h>
#include <string.h>
#ifdef XOS_OBSERVATION_TRUST_GUEST
#include <xos/sdk.hpp>
#endif

namespace {
using native_tls::trust_store;
using native_tls::trust_store_pin;
using native_tls::trust_store_result;
using xos::observation::status;
using xos::observation::trust_snapshot;
unsigned checks = 0;

bool check(const char* name, bool passed) {
    printf("OBS_TRUST_CHECK %s %s\n", name, passed ? "PASS" : "FAIL");
    if (passed) ++checks;
    return passed;
}

bool zero(const trust_snapshot& value) {
    unsigned char present = 0;
    for (unsigned char byte : value.sha256) present |= byte;
    return value.generation == 0 && present == 0;
}

bool matches(const trust_snapshot& value, const trust_store_pin& pin) {
    return value.generation == pin.generation && !memcmp(value.sha256, pin.sha256, 32);
}

bool unavailable(const void* context) {
    trust_snapshot value;
    memset(&value, 0xa5, sizeof value);
    return native_tls::capture_trust_observation(context, value) == status::unavailable && zero(value);
}

bool selected(const void* context, const trust_store_pin& pin) {
    trust_snapshot value{};
    if (native_tls::capture_trust_observation(context, value) != status::ok || !matches(value, pin))
        return false;
    printf("OBS_TRUST_ID generation=%lu sha256=", static_cast<unsigned long>(value.generation));
    for (unsigned char byte : value.sha256) printf("%02x", static_cast<unsigned>(byte));
    putchar('\n');
    // A consumer receives a copy and cannot rewrite the selected store.
    memset(&value, 0, sizeof value);
    return native_tls::capture_trust_observation(context, value) == status::ok && matches(value, pin);
}
#ifdef XOS_OBSERVATION_TRUST_GUEST
bool production_record(const void* context, status expected, unsigned number, xos::u64 epoch) {
    using namespace xos;
    observation::sources source;
    source.trust_context = context;
    source.trust_capture = native_tls::capture_trust_observation;
    const i64 now = sdk::syscall(sys_clock_monotonic);
    if (now < 0) return false;
    const u64 deadline = static_cast<u64>(now) + 1'000'000'000;
    observation::response value{};
    const status result = observation::sources::capture(&source, observation::kind::trust, deadline, value);
    if (result != expected) return false;
    value.version = observation::version; value.size = sizeof value;
    value.subject = observation::kind::trust; value.outcome = result;
    value.sequence = value.observation_id = number;
    value.server_pid = value.caller_pid = sdk::pid(); value.server_epoch = epoch;
    value.observed_at_ns = static_cast<u64>(now); value.valid_until_ns = deadline;
    // The local test envelope identifies this actual provider instance. Remote
    // authorization/transport is covered by the separate ordinary client gate.
    fflush(stdout);
    sdk::print("OBS_JSON ");
    return observation::print_json(value) == status::ok;
}
#endif
}

int main() {
    trust_store first;
    trust_store_pin identity = trust_pin_7;
    if (!check("null_context_zeroed", unavailable(nullptr)) ||
        !check("empty_store_zeroed", unavailable(&first)) ||
        !check("empty_identity_zeroed", !first.capture_pin(identity) && !identity.generation &&
               !memcmp(identity.sha256, trust_snapshot{}.sha256, 32))) return 1;

    auto wrong = trust_pin_7;
    wrong.sha256[0] ^= 1;
    if (!check("wrong_digest_unavailable", first.load(trust_data_7, sizeof trust_data_7, wrong) ==
               trust_store_result::pin_mismatch && unavailable(&first)) ||
        !check("wrong_generation_unavailable", first.load(trust_data_7, sizeof trust_data_7, trust_pin_8) ==
               trust_store_result::pin_mismatch && unavailable(&first))) return 1;

    unsigned char malformed[sizeof trust_data_7];
    memcpy(malformed, trust_data_7, sizeof malformed);
    malformed[36] = 0; // Hash-consistent malformed DER must still have no identity.
    auto malformed_pin = trust_pin_7;
    size_t size = 0;
    if (!check("malformed_der_unavailable", psa_hash_compute(PSA_ALG_SHA_256, malformed,
               sizeof malformed, malformed_pin.sha256, sizeof malformed_pin.sha256, &size) == PSA_SUCCESS &&
               size == 32 && first.load(malformed, sizeof malformed, malformed_pin) ==
               trust_store_result::malformed_certificate && unavailable(&first))) return 1;

    auto expected = trust_pin_7;
    if (!check("verified_store_load", first.load(trust_data_7, sizeof trust_data_7, expected) ==
               trust_store_result::ok && first.ready() && first.anchor_count() == 1)) return 1;
    expected.generation = 999;
    memset(expected.sha256, 0, sizeof expected.sha256);
    if (!check("verified_pin_owned_copy", first.capture_pin(identity) && identity.generation == 7 &&
               !memcmp(identity.sha256, trust_pin_7.sha256, 32) && first.generation() == 7 &&
               selected(&first, trust_pin_7)) ||
        !check("reload_preserves_loaded_identity", first.load(trust_data_8, sizeof trust_data_8, trust_pin_8) ==
               trust_store_result::already_loaded && selected(&first, trust_pin_7))) return 1;

    trust_store second;
    if (!check("replacement_store_load", second.load(trust_data_8, sizeof trust_data_8, trust_pin_8) ==
               trust_store_result::ok && second.ready() && second.anchor_count() == 1)) return 1;
    const void* active = &first;
    if (!check("selected_original", selected(active, trust_pin_7))) return 1;
    active = &second;
    if (!check("selected_replacement", selected(active, trust_pin_8))) return 1;
    active = &first;
    if (!check("authorized_rollback_selection", selected(active, trust_pin_7))) return 1;
    active = nullptr; // Detach before either borrowed store is destroyed.
    if (!check("detached_selection_unavailable", unavailable(active))) return 1;
#ifdef XOS_OBSERVATION_TRUST_GUEST
    xos::u64 epoch = 0;
    trust_store empty;
    if (xos::sdk::syscall(xos::sys_random_bytes, reinterpret_cast<xos::u64>(&epoch), sizeof epoch) || !epoch ||
        !check("production_source_records", production_record(&empty, status::unavailable, 1, epoch) &&
               production_record(&first, status::ok, 2, epoch) && production_record(&second, status::ok, 3, epoch) &&
               production_record(&first, status::ok, 4, epoch) && production_record(nullptr, status::unavailable, 5, epoch))) return 1;
#endif
    printf("OBS_TRUST_PASS checks=%u\n", checks);
    return 0;
}
