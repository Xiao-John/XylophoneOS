// SPDX-License-Identifier: Apache-2.0
#include "stream.hpp"
#include "installed_tls_pins.hpp"
#include <xos/net_service_client.hpp>
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

namespace {
constexpr xos::u64 second = 1'000'000'000;
__thread unsigned thread_value = 17;
unsigned constructor_value;

__attribute__((constructor)) void before_main() {
    constructor_value = thread_value;
    thread_value = 19;
}

xos::u64 now() {
    timespec value{};
    if (clock_gettime(CLOCK_MONOTONIC, &value) || value.tv_sec < 0) return 0;
    return static_cast<xos::u64>(value.tv_sec) * second + static_cast<xos::u64>(value.tv_nsec);
}

int fail(const char* phase, long value) {
    printf("INSTALLED_TLS_FAIL phase=%s value=%ld\n", phase, value);
    return 1;
}

void* worker(void*) {
    if (thread_value != 17) return reinterpret_cast<void*>(1);
    thread_value = 23;
    errno = EDOM;
    return thread_value == 23 && errno == EDOM ? nullptr : reinterpret_cast<void*>(2);
}

int gnu_runtime() {
    pthread_t thread{};
    errno = ERANGE;
    const int created = pthread_create(&thread, nullptr, worker, nullptr);
    if (!created) {
        void* result{};
        (void)pthread_join(thread, &result);
        return fail("unexpected-worker-without-unwinder", 0);
    }
    // This approved C-only closure deliberately has no libgcc_s unwinder.
    // GNU's existing pthread contract rejects worker creation with ENOTSUP.
    // Qualify the main-thread GNU startup/TLS, never pretend a worker ran.
    if (constructor_value != 17 || thread_value != 19 || created != ENOTSUP || errno != ERANGE)
        return fail("gnu-main-tls-or-thread-denial", created);
    printf("INSTALLED_GNU_RUNTIME_PASS pid=%ld constructor=%u main_tls=%u pthread_create=ENOTSUP\n",
           static_cast<long>(getpid()), constructor_value, thread_value);
    return 0;
}

long lease(xos::u64 pid, xos::net2::lease_snapshot& result) {
    xos::net2::session_client session;
    long status = session.connect(pid);
    if (status) return status;
    xos::net2::config_snapshot config{};
    status = session.configuration(now() + 3 * second, config);
    if (status) return status;
    if (config.mode != xos::net2::network_mode::dhcp) return -1;
    status = session.lease_status(now() + 3 * second, result);
    if (!status && (result.epoch != config.epoch || result.address != config.address ||
                   result.mask != config.mask || result.gateway != config.gateway || result.resolver != config.resolver))
        return -2;
    return status;
}

int read_exact(native_tls::stream& stream, const char* expected) {
    unsigned char data[128]{};
    const size_t size = strlen(expected);
    if (size > sizeof data) return -1;
    size_t used = 0;
    while (used < size) {
        const int result = stream.read(data + used, size - used);
        if (result <= 0) return result ? result : -1;
        used += static_cast<size_t>(result);
    }
    return memcmp(data, expected, size) ? -2 : 0;
}
}

int main(int argc, char** argv) {
    setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 4 || strlen(argv[3]) != 32 || strspn(argv[3], "0123456789abcdef") != 32)
        return fail("arguments", argc);
    const char* mode = argv[1];
    char* end{};
    const auto pid = strtoul(argv[2], &end, 10);
    if (!pid || !*argv[2] || *end) return fail("service-pid", 0);
    if (gnu_runtime()) return 1;
    const bool second_root = !strcmp(mode, "trust2");
    const bool stale_pin = !strcmp(mode, "stale-pin");
    native_tls::trust_store store;
    const auto& pin = second_root || stale_pin ? installed_tls_pin_2 : installed_tls_pin_1;
    const char* roots = second_root ? "/usr/share/xos/p1_k4/roots-2.bin" : "/usr/share/xos/p1_k4/roots-1.bin";
    const auto loaded = store.load_file(roots, pin);
    if (stale_pin) {
        if (loaded != native_tls::trust_store_result::pin_mismatch || store.ready())
            return fail("stale-pin", static_cast<long>(loaded));
        printf("INSTALLED_TLS_PASS mode=stale-pin generation=2 rejected_before_network=1\n");
        return 0;
    }
    if (loaded != native_tls::trust_store_result::ok || store.anchor_count() != 1)
        return fail("trust-load", static_cast<long>(loaded));
    xos::net2::lease_snapshot first{};
    long status = lease(pid, first);
    if (!strcmp(mode, "stale-pid")) {
        if (status != xos::net2::denied) return fail("stale-pid", status);
        printf("INSTALLED_TLS_PASS mode=stale-pid expected_service=%lu denied=1\n", pid);
        return 0;
    }
    const auto acquisition_deadline = now() + 35 * second;
    while ((status == xos::net2::closed || (!status && !first.address)) && now() < acquisition_deadline) {
        if (xos::sdk::syscall(xos::sys_sleep_until, now() + second / 5)) return fail("lease-wait", -1);
        status = lease(pid, first);
    }
    if (status || !first.address || first.expires <= now() || first.server != 0x0a000202)
        return fail("dhcp-lease", status);
    printf("INSTALLED_LEASE service=%lu epoch=%lu address=%u server=%u expires=%lu generation=%lu\n",
           pid, first.epoch, first.address, first.server, first.expires, store.generation());
    const auto began = now();
    const auto deadline = began + 29 * second;
    native_tls::stream stream;
    xos::net2::lease_snapshot unavailable{};
    unavailable.epoch = 1234;
    if (stream.lease_status(unavailable) != xos::net2::closed || unavailable.epoch)
        return fail("lease-before-handshake", -1);
    const int connected = stream.connect(pid, 0x0a000202, 443, "tls.xos.test", store, deadline,
                                         native_tls::route_source::net2_dns);
    if (connected) return fail("tls-connect", connected);
    const auto certificate = stream.verified_peer_leaf_der();
    if (!certificate.data || !certificate.size) return fail("verified-certificate", 0);
    char message[128]{};
    const int size = snprintf(message, sizeof message, "%s %s\n", mode, argv[3]);
    if (size <= 0 || static_cast<size_t>(size) >= sizeof message ||
        stream.write(reinterpret_cast<const unsigned char*>(message), static_cast<size_t>(size)) != size)
        return fail("tls-write", size);
    snprintf(message, sizeof message, "ready %s\n", argv[3]);
    if (const int result = read_exact(stream, message)) return fail("tls-challenge", result);
    printf("INSTALLED_TLS_READY mode=%s nonce=%s service=%lu epoch=%lu\n", mode, argv[3], pid, first.epoch);
    if (!strcmp(mode, "renew")) {
        snprintf(message, sizeof message, "renew %s\n", argv[3]);
        if (const int result = read_exact(stream, message)) return fail("renew-live-stream", result);
        xos::net2::lease_snapshot renewed{};
        status = stream.lease_status(renewed);
        if (status || renewed.epoch != first.epoch || renewed.expires <= first.expires ||
            renewed.address != first.address || renewed.server != first.server || renewed.mask != first.mask ||
            renewed.gateway != first.gateway || renewed.resolver != first.resolver)
            return fail("renew-authority", status);
        printf("INSTALLED_RENEW epoch=%lu old_expires=%lu new_expires=%lu live_stream=1 same_session=1\n",
               renewed.epoch, first.expires, renewed.expires);
    } else if (!strcmp(mode, "expire") || !strcmp(mode, "stop") || !strcmp(mode, "death")) {
        if (!strcmp(mode, "expire")) {
            // The peer stops ACKs only after receiving our fresh TLS request.
            // Inspect current authority through this same authenticated
            // session, after any ACKs issued during the handshake were read.
            xos::net2::lease_snapshot armed{};
            status = stream.lease_status(armed);
            if (status || armed.epoch != first.epoch || armed.address != first.address ||
                armed.server != first.server || armed.expires <= now() || armed.expires >= deadline)
                return fail("expiry-authority", status);
            first = armed;
            printf("INSTALLED_EXPIRY_ARMED epoch=%lu expires=%lu same_session=1\n", first.epoch, first.expires);
        }
        unsigned char byte{};
        const int result = stream.read(&byte, 1);
        const auto finished = now();
        if (result >= 0 || finished >= deadline || finished <= began)
            return fail("bounded-retirement", result);
        if (!strcmp(mode, "expire") && (finished < first.expires || finished - first.expires > 3 * second))
            return fail("lease-expiry-bound", static_cast<long>(finished - first.expires));
        printf("INSTALLED_TLS_PASS mode=%s status=%d elapsed_ns=%lu deadline=%lu finished=%lu expires=%lu\n",
               mode, result, finished - began, deadline, finished, first.expires);
        return 0;
    } else if (strcmp(mode, "once") && strcmp(mode, "trust2")) return fail("mode", 0);
    unsigned char final_byte{};
    if (const int result = stream.read(&final_byte, 1)) return fail("peer-close-notify", result);
    if (const int result = stream.finish()) return fail("tls-close-notify", result);
    unavailable.epoch = 1234;
    if (stream.lease_status(unavailable) != xos::net2::closed || unavailable.epoch)
        return fail("lease-after-finish", -1);
    printf("INSTALLED_TLS_PASS mode=%s nonce=%s generation=%lu epoch=%lu\n",
           mode, argv[3], store.generation(), first.epoch);
    return 0;
}
