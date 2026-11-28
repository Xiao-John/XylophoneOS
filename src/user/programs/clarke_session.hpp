// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../../ports/webkit/browser/installation.hpp"
#include "../../ports/webkit/browser/transport.hpp"
#include <xos/fault_sha256.hpp>
#include <xos/net_service_client.hpp>

namespace xos::clarke {
class session {
public:
    explicit session(const installation& installed) : installed_(installed) { }
    bool run(u64 service, const char* url, bool diagnostics) {
        if (ui_.pid || broker_.pid || renderer_.pid || !service || !url) return false;
        service_ = service; diagnostics_ = diagnostics; fatal_ = false; phase_ = phase::idle;
        navigation_ = last_navigation_ = 0;
        before_ = sdk::stats();
        net2::peer_policy_snapshot policy{};
        if (authority_.connect(service_) || authority_.peer_policy(net2::peer_policy_action::query, 0,
                deadline_after(bootstrap_ns), policy)) {
            sdk::print("CLARKE_SESSION_FAILED stage=controller_policy\n"); authority_.close(); return false;
        }
        baseline_revoked_ = policy.occupied;
        if (!launch(ui_, role::ui, installed_.ui, url)) return stop();
        sdk::print("CLARKE_SESSION_READY ui="); sdk::decimal(ui_.pid); sdk::print("\n");
        bool closing = false;
        while (!fatal_ && !closing) {
            const i64 received = receive_now(ui_.channel, incoming_);
            if (!received) {
                if (!valid_intent(incoming_, last_navigation_, navigation_)) { fatal_ = true; break; }
                if (incoming_.action == operation::close) {
                    outgoing_ = {}; outgoing_.action = operation::close;
                    if (!send_packet(ui_.channel, outgoing_, deadline_after(bootstrap_ns))) { fatal_ = true; break; }
                    closing = true; break;
                }
                if (incoming_.action == operation::navigate) {
                    // finish may use scratch packets; preserve the new bounded URL.
                    const u64 next = incoming_.navigation; const u32 length = incoming_.length;
                    for (u32 i = 0; i < length; ++i) next_url_[i] = incoming_.data[i];
                    next_url_[length] = 0;
                    if (!finish(outcome::cancelled, false)) break;
                    navigation_ = last_navigation_ = next; navigation_before_ = sdk::stats();
                    deadline_ = deadline_after(navigation_ns); phase_ = phase::document;
                    document_size_ = document_used_ = 0; document_hash_ = sha256{};
                    if (!launch(broker_, role::network, installed_.network, nullptr)) { (void)finish(outcome::network); continue; }
                    outgoing_ = {}; outgoing_.action = operation::fetch; outgoing_.navigation = navigation_; outgoing_.length = length;
                    for (u32 i = 0; i < length; ++i) outgoing_.data[i] = static_cast<u8>(next_url_[i]);
                    if (!send_packet(broker_.channel, outgoing_, deadline_)) (void)finish(outcome::network);
                } else if (incoming_.action == operation::cancel) {
                    (void)finish(outcome::cancelled);
                } else if (incoming_.action == operation::presented) {
                    if (phase_ != phase::presented || __builtin_memcmp(incoming_.data, frame_digest_, 32)) { fatal_ = true; break; }
                    if (!retire(renderer_, false, true) || !retire(broker_, true, false) || !settle(outcome::ok)) break;
                    phase_ = phase::idle;
                }
            } else if (received != process_error_would_block) { fatal_ = true; break; }
            if (phase_ != phase::idle) {
                const u64 clock = now();
                if (!clock || clock >= deadline_) { (void)finish(outcome::deadline); continue; }
                child& worker = phase_ == phase::document ? broker_ : renderer_;
                // A renderer that has sent its frame may already have exited;
                // its final message was acknowledged before it was allowed to exit.
                if (phase_ != phase::presented) {
                    const i64 received_worker = receive_now(worker.channel, incoming_);
                    if (!received_worker) {
                        if (!worker_message(incoming_)) (void)finish(phase_ == phase::document ? outcome::network : outcome::renderer);
                    } else if (received_worker != process_error_would_block) {
                        (void)finish(phase_ == phase::document ? outcome::network : outcome::renderer);
                    }
                }
            }
            if (!fatal_) {
                const u64 wait = deadline_after(control_quantum_ns);
                const i64 waited = sdk::ipc_wait_until(ui_.channel.receive, ipc_wait_mode::receive, wait);
                if (waited && waited != thread_error_timeout) { fatal_ = true; break; }
            }
        }
        return stop(closing);
    }
private:
    enum class phase { idle, document, frame, presented };
    struct child {
        u64 pid = 0;
        role kind{};
        ipc_channel channel{};
        u32 bootstrap_send = 0, bootstrap_receive = 0;
        bool revoked = false, started = false;
    };
    static i64 prepare_child(u64 pid, void* context) {
        return static_cast<session*>(context)->prepare(pid);
    }
    i64 prepare(u64 pid) {
        auto& child = *preparing_; child.pid = pid;
        i64 result = sdk::set_process_budget(pid, preparing_image_->limits);
        process_budget_snapshot budget{};
        if (!result) result = sdk::query_process_budget(pid, budget);
        if (!result && (budget.version != process_budget_version || budget.size != sizeof(budget) ||
            budget.pid != pid || budget.owner_pid != pid || !(budget.flags & process_budget_active) ||
            __builtin_memcmp(&budget.limits, &preparing_image_->limits, sizeof(budget.limits)))) result = process_error_denied;
        if (result) return result;
        const channel_create incoming{channel_version, sizeof(channel_create), sdk::pid(), pid, sizeof(bootstrap), 0};
        result = sdk::channel_open(incoming);
        if (result < 0) return result;
        child.bootstrap_send = static_cast<u32>(result);
        const channel_create outgoing{channel_version, sizeof(channel_create), pid, sdk::pid(), sizeof(bootstrap), 0};
        result = sdk::channel_open(outgoing);
        if (result < 0) return result;
        child.bootstrap_receive = static_cast<u32>(result);
        if (child.kind == role::renderer) {
            // A lost reply may mean the denial committed. Mark before sending.
            child.revoked = true;
            result = revoke(pid);
            if (result) return result;
        }
        sdk::print("CLARKE_PREPARED navigation="); sdk::decimal(navigation_);
        sdk::print(" role="); sdk::decimal(static_cast<u32>(child.kind)); sdk::print(" pid="); sdk::decimal(pid);
        sdk::print(" domain="); sdk::decimal(budget.domain_id); sdk::print(" pages="); sdk::decimal(budget.limits.pages);
        sdk::print(" threads="); sdk::decimal(budget.limits.threads); sdk::print(" revoked="); sdk::decimal(child.revoked); sdk::print("\n");
        return 0;
    }
    bool reconnectable(i64 value) const { return value == net2::closed || value == net2::io || value == net2::timeout; }
    i64 revoke(u64 pid) {
        for (unsigned attempt = 0; attempt < 2; ++attempt) {
            net2::message input{}, output{}; input.action = net2::operation::revoke_peer;
            input.object = pid; input.deadline = deadline_after(bootstrap_ns);
            const i64 result = authority_.request(input, output);
            if (!attempt && reconnectable(result)) { authority_.close(); if (!authority_.connect(service_)) continue; }
            return result;
        }
        return net2::closed;
    }
    bool release(child& value) {
        if (!value.revoked) return true;
        for (unsigned attempt = 0; attempt < 2; ++attempt) {
            net2::peer_policy_snapshot policy{};
            const i64 result = authority_.peer_policy(net2::peer_policy_action::release_retired, value.pid,
                deadline_after(bootstrap_ns), policy);
            if (!result) { value.revoked = false; return true; }
            if (!attempt && reconnectable(result)) { authority_.close(); if (!authority_.connect(service_)) continue; }
            fatal_ = true; return false;
        }
        fatal_ = true; return false;
    }
    void close_bootstrap(child& value) {
        if (value.bootstrap_send) (void)sdk::channel_close(value.bootstrap_send);
        if (value.bootstrap_receive) (void)sdk::channel_close(value.bootstrap_receive);
        value.bootstrap_send = value.bootstrap_receive = 0;
    }
    static void pid_text(u64 pid, char* result) {
        char reverse[24]; u32 length = 0;
        do { reverse[length++] = static_cast<char>('0' + pid % 10); pid /= 10; } while (pid);
        for (u32 i = 0; i < length; ++i) result[i] = reverse[length - i - 1];
        result[length] = 0;
    }
    bool launch(child& value, role kind, const executable& image, const char* url) {
        if (value.pid) { fatal_ = true; return false; }
        value = {}; value.kind = kind; preparing_ = &value; preparing_image_ = &image;
        char controller[24]; pid_text(sdk::pid(), controller);
        const char* arguments[]{image.path, controller, url};
        sdk::spawn_options options{}; options.stdio[0] = -2;
        options.prepare_child = prepare_child; options.prepare_context = this;
        execution::launch_abort_outcome aborted{};
        const i64 pid = execution::spawn_verified_static_file(image.path, url ? 3 : 2, arguments, options, image.receipt, aborted);
        preparing_ = nullptr; preparing_image_ = nullptr;
        if (pid < 0) {
            close_bootstrap(value);
            const bool known = aborted.version == 1 && aborted.size == sizeof(aborted) &&
                aborted.pid && (!value.pid || value.pid == aborted.pid) && aborted.never_started == 1 &&
                aborted.abort_attempted == 1 && aborted.abort_result == 0;
            sdk::print("CLARKE_START_FAILED result="); sdk::signed_decimal(pid);
            sdk::print(" pid="); sdk::decimal(aborted.pid); sdk::print(" never_started="); sdk::decimal(aborted.never_started);
            sdk::print(" abort_attempted="); sdk::decimal(aborted.abort_attempted);
            sdk::print(" abort_result="); sdk::signed_decimal(aborted.abort_result); sdk::print(" confirmed="); sdk::decimal(known); sdk::print("\n");
            if (aborted.pid && !known) { fatal_ = true; return false; }
            if (value.revoked && (!known || !release(value))) { fatal_ = true; return false; }
            value = {}; return false;
        }
        if (value.pid != static_cast<u64>(pid) || aborted.pid != value.pid || aborted.never_started) {
            fatal_ = true; return false;
        }
        value.started = true;
        bootstrap sent{}; sent.kind = kind; sent.controller = sdk::pid();
        sent.network = kind == role::ui ? 0 : service_; sent.diagnostics = diagnostics_;
        if (sdk::write(value.bootstrap_send, &sent, sizeof(sent)) != sizeof(sent)) { fatal_ = true; return false; }
        bootstrap received{}; const u64 deadline = deadline_after(bootstrap_ns);
        for (;;) {
            const u64 clock = now(); if (!clock || clock >= deadline) { fatal_ = true; return false; }
            const i64 result = sdk::read(value.bootstrap_receive, &received, sizeof(received));
            if (result == sizeof(received)) break;
            if (result != process_error_would_block || sdk::channel_wait(value.bootstrap_receive, deadline)) {
                fatal_ = true; return false;
            }
        }
        value.channel = received.endpoints; received.endpoints = {};
        if (__builtin_memcmp(&received, &sent, sizeof(sent)) || !peer_matches(value.channel, value.pid) ||
            !receive_packet(value.channel, incoming_, deadline) || incoming_.action != operation::ready ||
            incoming_.navigation || incoming_.length || incoming_.result || incoming_.offset != static_cast<u32>(kind)) {
            fatal_ = true; return false;
        }
        close_bootstrap(value); return true;
    }
    bool retire(child& value, bool cancel, bool success_required) {
        if (!value.pid) return true;
        if (!value.started) { fatal_ = true; return false; }
        process_status status{};
        i64 result = sdk::wait_flags(value.pid, status, process_wait_nonblocking);
        if (result == process_error_would_block && cancel) (void)sdk::syscall(sys_process_cancel, value.pid);
        const u64 deadline = deadline_after(bootstrap_ns);
        while (result == process_error_would_block) {
            const u64 clock = now();
            if (!clock || clock >= deadline) { fatal_ = true; return false; }
            (void)sdk::syscall(sys_sleep_until, clock + control_quantum_ns < deadline ? clock + control_quantum_ns : deadline);
            result = sdk::wait_flags(value.pid, status, process_wait_nonblocking);
        }
        if (result || status.version != 1 || status.pid != value.pid) { fatal_ = true; return false; }
        sdk::print("CLARKE_REAPED navigation="); sdk::decimal(navigation_); sdk::print(" role="); sdk::decimal(static_cast<u32>(value.kind));
        sdk::print(" pid="); sdk::decimal(value.pid); sdk::print(" outcome="); sdk::decimal(static_cast<u32>(status.outcome));
        sdk::print(" code="); sdk::signed_decimal(status.code); sdk::print("\n");
        close_pair(value.channel); close_bootstrap(value);
        if (!release(value)) return false;
        const bool good = !success_required || (status.outcome == process_outcome::exited && status.code == 0);
        value = {};
        if (!good) fatal_ = true;
        return good;
    }
    bool renderer_policy() {
        if (!receive_packet(renderer_.channel, incoming_, deadline_) || incoming_.action != operation::renderer_policy ||
            incoming_.navigation || incoming_.length || incoming_.offset ||
            (incoming_.result != net2::denied && incoming_.result != net2::closed)) return false;
        net2::peer_policy_snapshot policy{};
        if (authority_.peer_policy(net2::peer_policy_action::query, 0, deadline_after(bootstrap_ns), policy) ||
            policy.occupied != baseline_revoked_ + 1) return false;
        if (diagnostics_) {
            outgoing_ = {}; outgoing_.action = operation::network_probe; outgoing_.navigation = navigation_;
            outgoing_.length = sizeof(renderer_.pid); __builtin_memcpy(outgoing_.data, &renderer_.pid, sizeof(renderer_.pid));
            if (!send_packet(broker_.channel, outgoing_, deadline_) || !receive_packet(broker_.channel, incoming_, deadline_) ||
                incoming_.action != operation::network_probe || incoming_.navigation != navigation_ || incoming_.length ||
                incoming_.offset != 1 || incoming_.result != net2::denied) return false;
        }
        return true;
    }
    bool worker_message(const packet& value) {
        if (value.navigation != navigation_ || value.result) return false;
        if (phase_ == phase::document) {
            if (value.action == operation::document_begin) {
                if (document_size_ || value.length || !value.offset || value.offset > document_limit) return false;
                document_size_ = value.offset; return true;
            }
            if (value.action == operation::document_chunk) {
                if (!document_size_ || value.offset != document_used_ || !value.length || value.length > document_size_ - document_used_) return false;
                __builtin_memcpy(document_ + document_used_, value.data, value.length); document_hash_.update(value.data, value.length);
                document_used_ += value.length; return true;
            }
            if (value.action != operation::document_end || !document_size_ || document_used_ != document_size_ ||
                value.offset != document_size_ || value.length != 32) return false;
            document_hash_.finish(document_digest_);
            if (__builtin_memcmp(value.data, document_digest_, 32)) return false;
            if (!launch(renderer_, role::renderer, installed_.renderer, nullptr) || !renderer_policy()) return false;
            outgoing_ = {}; outgoing_.action = operation::document_begin; outgoing_.navigation = navigation_; outgoing_.offset = document_size_;
            if (!send_packet(renderer_.channel, outgoing_, deadline_)) return false;
            for (u32 offset = 0; offset < document_size_;) {
                outgoing_ = {}; outgoing_.action = operation::document_chunk; outgoing_.navigation = navigation_; outgoing_.offset = offset;
                outgoing_.length = document_size_ - offset < payload_bytes ? document_size_ - offset : payload_bytes;
                __builtin_memcpy(outgoing_.data, document_ + offset, outgoing_.length);
                if (!send_packet(renderer_.channel, outgoing_, deadline_)) return false;
                offset += outgoing_.length;
            }
            outgoing_ = {}; outgoing_.action = operation::document_end; outgoing_.navigation = navigation_;
            outgoing_.offset = document_size_; outgoing_.length = 32; __builtin_memcpy(outgoing_.data, document_digest_, 32);
            if (!send_packet(renderer_.channel, outgoing_, deadline_)) return false;
            phase_ = phase::frame; frame_used_ = 0; frame_began_ = false; frame_hash_ = sha256{}; return true;
        }
        if (phase_ != phase::frame) return false;
        if (value.action == operation::frame_begin) {
            frame_info info{};
            if (frame_began_ || value.offset || value.length != sizeof(info)) return false;
            __builtin_memcpy(&info, value.data, sizeof(info));
            if (info.width != viewport_width || info.height != viewport_height || info.stride != viewport_width * 4 || info.bytes != frame_bytes) return false;
            frame_began_ = true;
        } else if (value.action == operation::frame_chunk) {
            if (!frame_began_ || value.offset != frame_used_ || !value.length || value.length > frame_bytes - frame_used_) return false;
            frame_hash_.update(value.data, value.length); frame_used_ += value.length;
        } else if (value.action == operation::frame_end) {
            if (!frame_began_ || frame_used_ != frame_bytes || value.offset != frame_bytes || value.length != 32) return false;
            frame_hash_.finish(frame_digest_);
            if (__builtin_memcmp(value.data, frame_digest_, 32)) return false;
            outgoing_ = {}; outgoing_.action = operation::frame_accepted; outgoing_.navigation = navigation_; outgoing_.length = 32;
            __builtin_memcpy(outgoing_.data, frame_digest_, 32);
            if (!send_packet(renderer_.channel, outgoing_, deadline_)) return false;
            phase_ = phase::presented;
        } else return false;
        return send_packet(ui_.channel, value, deadline_);
    }
    bool settle(outcome result) {
        net2::peer_policy_snapshot policy{};
        if (authority_.peer_policy(net2::peer_policy_action::query, 0, deadline_after(bootstrap_ns), policy) ||
            policy.occupied != baseline_revoked_) { fatal_ = true; return false; }
        const auto after = sdk::stats();
        const bool counts = after.tasks == navigation_before_.tasks && after.completions == navigation_before_.completions;
        process_budget_snapshot ui_budget{};
        i64 ui_status = process_error_state;
        if (diagnostics_) {
            ui_status = sdk::query_process_budget(ui_.pid, ui_budget);
            if (!ui_status && (ui_budget.version != process_budget_version || ui_budget.size != sizeof(ui_budget) ||
                ui_budget.pid != ui_.pid || ui_budget.owner_pid != ui_.pid ||
                !(ui_budget.flags & process_budget_active))) ui_status = process_error_state;
        }
        sdk::print("CLARKE_NAVIGATION_DONE navigation="); sdk::decimal(navigation_); sdk::print(" result="); sdk::signed_decimal(static_cast<i32>(result));
        sdk::print(" lifetimes_reaped="); sdk::decimal(counts); sdk::print(" revoked="); sdk::decimal(policy.occupied);
        sdk::print(" free_pages="); sdk::decimal(after.free_pages);
        if (diagnostics_) {
            sdk::print(" ui_budget_status="); sdk::signed_decimal(ui_status);
            sdk::print(" ui_pages="); sdk::decimal(ui_status ? 0 : ui_budget.usage.pages);
            sdk::print(" ui_threads="); sdk::decimal(ui_status ? 0 : ui_budget.usage.threads);
        }
        sdk::print("\n");
        if (diagnostics_ && !counts) { fatal_ = true; return false; }
        return true;
    }
    bool finish(outcome result, bool notify = true) {
        if (phase_ == phase::idle) return true;
        const bool renderer = retire(renderer_, true, false);
        const bool broker = retire(broker_, true, false);
        if (!renderer || !broker || !settle(result)) return false;
        phase_ = phase::idle; document_used_ = document_size_ = frame_used_ = 0;
        if (notify && ui_.pid) {
            outgoing_ = {}; outgoing_.action = operation::status; outgoing_.navigation = navigation_;
            outgoing_.result = static_cast<i32>(result);
            if (!send_packet(ui_.channel, outgoing_, deadline_after(bootstrap_ns))) { fatal_ = true; return false; }
        }
        return true;
    }
    bool stop(bool graceful_ui = false) {
        (void)finish(outcome::cancelled, false);
        const bool renderer = retire(renderer_, true, false), broker = retire(broker_, true, false);
        const bool ui = retire(ui_, !graceful_ui, graceful_ui);
        authority_.close();
        bool restored = false; process_stats after{}; const u64 deadline = deadline_after(bootstrap_ns);
        do {
            after = sdk::stats();
            restored = after.tasks == before_.tasks && after.completions == before_.completions && after.free_pages == before_.free_pages;
            if (restored || !now() || now() >= deadline) break;
            (void)sdk::syscall(sys_sleep_until, deadline_after(control_quantum_ns));
        } while (true);
        sdk::print("CLARKE_SESSION_RESOURCES before_pages="); sdk::decimal(before_.free_pages);
        sdk::print(" after_pages="); sdk::decimal(after.free_pages); sdk::print(" restored="); sdk::decimal(restored); sdk::print("\n");
        const bool success = !fatal_ && renderer && broker && ui && (!diagnostics_ || restored);
        sdk::print(success ? "CLARKE_SESSION_RELEASED\n" : "CLARKE_SESSION_FAILED\n"); return success;
    }
    const installation& installed_;
    net2::session_client authority_;
    child ui_{}, broker_{}, renderer_{};
    child* preparing_ = nullptr;
    const executable* preparing_image_ = nullptr;
    u64 service_ = 0, navigation_ = 0, last_navigation_ = 0, deadline_ = 0;
    u32 baseline_revoked_ = 0, document_size_ = 0, document_used_ = 0, frame_used_ = 0;
    bool diagnostics_ = false, fatal_ = false, frame_began_ = false;
    phase phase_ = phase::idle;
    process_stats before_{}, navigation_before_{};
    char next_url_[url_limit + 1]{};
    u8 document_[document_limit]{}, document_digest_[32]{}, frame_digest_[32]{};
    sha256 document_hash_, frame_hash_;
    packet incoming_{}, outgoing_{};
};
}
