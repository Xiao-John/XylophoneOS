#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host-only executable reference for the registered IPC v1 contract.

This model is not linked into XOS, is not an SDK backend, and provides no
evidence about kernel safety or performance.
"""
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ipc_v1_manifest import ipc_v1_manifest_entry


ipc_v1_max_message_bytes = 256
ipc_v1_max_handles_per_process = 8
ipc_v1_max_endpoints_system = 32
ipc_v1_max_pending_calls = 32
ipc_v1_max_queue_per_endpoint = 8
ipc_v1_max_reply_tokens_per_process = 8
ipc_v1_deadline_poll = 0
ipc_v1_deadline_infinite = (1 << 64) - 1
ipc_v1_feature_known_mask = 0x1f


class ipc_v1_error(IntEnum):
    invalid_handle = -101
    denied = -102
    invalid_argument = -103
    unsupported = -104
    would_block = -105
    queue_full = -106
    resources = -107
    closed = -108
    timeout = -109
    buffer_too_small = -110
    stale_token = -111
    state = -112


class rights(IntFlag):
    call = 1
    receive = 2
    manage = 4
    delegate = 8


class phase(IntEnum):
    not_delivered = 0
    delivered = 1
    replied = 2
    cancelled = 3
    closed = 4
    result_unknown = 5
    timed_out = 6


@dataclass
class capability:
    endpoint_id: int
    holder_pid: int
    granted: rights
    badge: int


@dataclass
class call_record:
    call_id: int
    endpoint_id: int
    caller_pid: int
    label: int
    payload: bytes
    reply_capacity: int
    deadline_ns: int
    state: phase = phase.not_delivered
    receiver_pid: int = 0
    reply_token: int = 0
    reply_label: int = 0
    reply_payload: bytes = b""


@dataclass
class receive_waiter:
    waiter_id: int
    endpoint_id: int
    receiver_pid: int
    badge: int
    capacity: int
    deadline_ns: int
    done: bool = False
    error: ipc_v1_error | None = None
    call_id: int = 0
    required_length: int = 0
    result: dict | None = None


@dataclass
class endpoint:
    endpoint_id: int
    open: bool = True
    queued_calls: deque = field(default_factory=deque)
    waiters: deque = field(default_factory=deque)


class reference_model:
    def __init__(self):
        self.endpoints = {}
        self.capabilities = {}
        self.calls = {}
        self.tokens = {}
        self.receive_waiters = {}
        self.next_endpoint_id = 1
        self.next_handle = 1
        self.next_call_id = 1
        self.next_token = 1
        self.next_waiter_id = 1

    @staticmethod
    def query_features():
        return {
            "known": ipc_v1_feature_known_mask,
            "supported": 0x3,
            "limits": (ipc_v1_max_message_bytes,
                       ipc_v1_max_handles_per_process,
                       ipc_v1_max_endpoints_system,
                       ipc_v1_max_pending_calls,
                       ipc_v1_max_queue_per_endpoint,
                       ipc_v1_max_reply_tokens_per_process),
        }

    def _new_handle(self, endpoint_id, holder_pid, granted, badge):
        handle = self.next_handle
        self.next_handle += 1
        self.capabilities[handle] = capability(endpoint_id, holder_pid, granted, badge)
        return handle

    def create(self, owner_pid, initial_rights=rights.call | rights.receive | rights.manage | rights.delegate):
        if owner_pid <= 0:
            return ipc_v1_error.invalid_argument
        if not initial_rights or int(initial_rights) & ~int(rights.call | rights.receive | rights.manage | rights.delegate):
            return ipc_v1_error.invalid_argument
        if sum(1 for item in self.endpoints.values() if item.open) >= ipc_v1_max_endpoints_system:
            return ipc_v1_error.resources
        owned = self._active_handle_count(owner_pid)
        if owned >= ipc_v1_max_handles_per_process:
            return ipc_v1_error.resources
        endpoint_id = self.next_endpoint_id
        self.next_endpoint_id += 1
        self.endpoints[endpoint_id] = endpoint(endpoint_id)
        return self._new_handle(endpoint_id, owner_pid, initial_rights, 0)

    def _authorized(self, pid, handle, required):
        cap = self.capabilities.get(handle)
        if cap is None:
            return None, ipc_v1_error.invalid_handle
        if cap.holder_pid != pid:
            return None, ipc_v1_error.denied
        obj = self.endpoints.get(cap.endpoint_id)
        if obj is None or not obj.open:
            return None, ipc_v1_error.closed
        if not (cap.granted & required):
            return None, ipc_v1_error.denied
        return cap, None

    def _active_handle_count(self, pid):
        return sum(1 for cap in self.capabilities.values()
                   if cap.holder_pid == pid and cap.granted)

    def delegate(self, pid, handle, target_pid, granted, badge):
        cap, error = self._authorized(pid, handle, rights.delegate)
        if error:
            return error
        if target_pid <= 0 or not granted or int(granted) & ~int(cap.granted):
            return ipc_v1_error.denied
        owned = self._active_handle_count(target_pid)
        if owned >= ipc_v1_max_handles_per_process:
            return ipc_v1_error.resources
        return self._new_handle(cap.endpoint_id, target_pid, granted, badge)

    def submit_call(self, pid, handle, label, payload, reply_capacity, deadline_ns, now_ns):
        cap, error = self._authorized(pid, handle, rights.call)
        if error:
            return error
        if (len(payload) > ipc_v1_max_message_bytes or
                reply_capacity > ipc_v1_max_message_bytes or
                deadline_ns < 0 or deadline_ns >= (1 << 64) or
                label < 0 or label >= (1 << 64)):
            return ipc_v1_error.invalid_argument
        obj = self.endpoints[cap.endpoint_id]
        self.expire(now_ns)
        active_calls = sum(1 for item in self.calls.values()
                           if item.state in (phase.not_delivered, phase.delivered))
        if active_calls >= ipc_v1_max_pending_calls:
            return ipc_v1_error.resources
        if not obj.waiters and deadline_ns == ipc_v1_deadline_poll:
            return ipc_v1_error.would_block
        if not obj.waiters and deadline_ns != ipc_v1_deadline_infinite and deadline_ns <= now_ns:
            return ipc_v1_error.timeout
        if not obj.waiters and len(obj.queued_calls) >= ipc_v1_max_queue_per_endpoint:
            return ipc_v1_error.queue_full
        call_id = self.next_call_id
        self.next_call_id += 1
        call = call_record(call_id, cap.endpoint_id, pid, label, bytes(payload),
                           reply_capacity, deadline_ns)
        self.calls[call_id] = call
        self._match_waiter(obj, call, cap.badge, now_ns)
        if call.state == phase.not_delivered:
            obj.queued_calls.append(call_id)
        return call_id

    def _match_waiter(self, obj, call, badge, now_ns):
        while obj.waiters:
            waiter = self.receive_waiters[obj.waiters[0]]
            if waiter.deadline_ns != ipc_v1_deadline_infinite and waiter.deadline_ns <= now_ns:
                obj.waiters.popleft()
                waiter.done = True
                waiter.error = ipc_v1_error.timeout
                continue
            if len(call.payload) > waiter.capacity:
                obj.waiters.popleft()
                waiter.done = True
                waiter.error = ipc_v1_error.buffer_too_small
                waiter.required_length = len(call.payload)
                continue
            if self._active_reply_token_count(waiter.receiver_pid) >= ipc_v1_max_reply_tokens_per_process:
                obj.waiters.popleft()
                waiter.done = True
                waiter.error = ipc_v1_error.resources
                continue
            obj.waiters.popleft()
            self._deliver(call, waiter, badge)
            return

    def begin_receive(self, pid, handle, capacity, deadline_ns, now_ns):
        cap, error = self._authorized(pid, handle, rights.receive)
        if error:
            return error
        if capacity < 0 or capacity > ipc_v1_max_message_bytes:
            return ipc_v1_error.invalid_argument
        if deadline_ns < 0 or deadline_ns >= (1 << 64):
            return ipc_v1_error.invalid_argument
        self.expire(now_ns)
        obj = self.endpoints[cap.endpoint_id]
        while obj.queued_calls:
            call_id = obj.queued_calls[0]
            call = self.calls[call_id]
            if call.state != phase.not_delivered:
                obj.queued_calls.popleft()
                continue
            if len(call.payload) > capacity:
                return {"error": ipc_v1_error.buffer_too_small,
                        "required_length": len(call.payload), "consumed": False}
            if self._active_reply_token_count(pid) >= ipc_v1_max_reply_tokens_per_process:
                return ipc_v1_error.resources
            obj.queued_calls.popleft()
            return self._deliver(call, None, cap.badge, pid)
        if deadline_ns == ipc_v1_deadline_poll:
            return ipc_v1_error.would_block
        if deadline_ns != ipc_v1_deadline_infinite and deadline_ns <= now_ns:
            return ipc_v1_error.timeout
        waiter_id = self.next_waiter_id
        self.next_waiter_id += 1
        waiter = receive_waiter(waiter_id, cap.endpoint_id, pid, cap.badge,
                                capacity, deadline_ns)
        self.receive_waiters[waiter_id] = waiter
        obj.waiters.append(waiter_id)
        return {"pending": waiter_id}

    def _deliver(self, call, waiter=None, badge=0, receiver_pid=0):
        if waiter is not None:
            receiver_pid = waiter.receiver_pid
            waiter.done = True
            waiter.call_id = call.call_id
        call.state = phase.delivered
        call.receiver_pid = receiver_pid
        token = self.next_token
        self.next_token += 1
        call.reply_token = token
        self.tokens[token] = call.call_id
        result = {"call_id": call.call_id, "label": call.label,
                  "payload": call.payload, "badge": badge, "reply_token": token}
        if waiter is not None:
            waiter.result = result
        return result

    def _active_reply_token_count(self, pid):
        return sum(1 for call_id in self.tokens.values()
                   if self.calls[call_id].receiver_pid == pid)

    def poll_receive(self, waiter_id):
        waiter = self.receive_waiters[waiter_id]
        if not waiter.done:
            return {"pending": waiter_id}
        if waiter.error:
            return {"error": waiter.error, "required_length": waiter.required_length,
                    "consumed": False}
        return waiter.result

    def reply(self, pid, token, label, payload):
        call_id = self.tokens.get(token)
        if call_id is None:
            return ipc_v1_error.stale_token
        call = self.calls[call_id]
        if call.receiver_pid != pid:
            return ipc_v1_error.denied
        if call.state != phase.delivered:
            return ipc_v1_error.stale_token
        if len(payload) > ipc_v1_max_message_bytes:
            return ipc_v1_error.invalid_argument
        if len(payload) > call.reply_capacity:
            return {"error": ipc_v1_error.buffer_too_small,
                    "required_length": len(payload), "token_live": True}
        call.reply_label = label
        call.reply_payload = bytes(payload)
        call.state = phase.replied
        del self.tokens[token]
        return {"label": label, "payload": call.reply_payload, "phase": phase.replied}

    def cancel_call(self, call_id):
        call = self.calls[call_id]
        if call.state == phase.not_delivered:
            call.state = phase.cancelled
            self._remove_queued(call)
            return phase.cancelled
        if call.state == phase.delivered:
            call.state = phase.result_unknown
            self.tokens.pop(call.reply_token, None)
            return phase.result_unknown
        return call.state

    def expire(self, now_ns):
        for obj in self.endpoints.values():
            for waiter_id in list(obj.waiters):
                waiter = self.receive_waiters[waiter_id]
                if waiter.deadline_ns != ipc_v1_deadline_infinite and waiter.deadline_ns <= now_ns:
                    obj.waiters.remove(waiter_id)
                    waiter.done = True
                    waiter.error = ipc_v1_error.timeout
        for call in self.calls.values():
            if (call.deadline_ns == ipc_v1_deadline_infinite or
                    call.deadline_ns > now_ns):
                continue
            if call.state == phase.not_delivered:
                call.state = phase.timed_out
                self._remove_queued(call)
            elif call.state == phase.delivered:
                call.state = phase.result_unknown
                self.tokens.pop(call.reply_token, None)

    def _remove_queued(self, call):
        obj = self.endpoints.get(call.endpoint_id)
        if obj is not None:
            try:
                obj.queued_calls.remove(call.call_id)
            except ValueError:
                pass

    def close(self, pid, handle):
        cap, error = self._authorized(pid, handle, rights.manage)
        if error:
            return error
        obj = self.endpoints[cap.endpoint_id]
        obj.open = False
        for call in self.calls.values():
            if call.endpoint_id != obj.endpoint_id:
                continue
            if call.state == phase.not_delivered:
                call.state = phase.closed
            elif call.state == phase.delivered:
                call.state = phase.result_unknown
                self.tokens.pop(call.reply_token, None)
        obj.queued_calls.clear()
        for waiter_id in obj.waiters:
            waiter = self.receive_waiters[waiter_id]
            waiter.done = True
            waiter.error = ipc_v1_error.closed
        obj.waiters.clear()
        for item in self.capabilities.values():
            if item.endpoint_id == obj.endpoint_id:
                item.granted = rights(0)
        return 0

    def reply_receive(self, pid, token, reply_label, reply_payload,
                      receive_handle, capacity, deadline_ns, now_ns):
        reply_result = self.reply(pid, token, reply_label, reply_payload)
        if isinstance(reply_result, ipc_v1_error) or isinstance(reply_result, dict) and "error" in reply_result:
            return {"error": reply_result, "reply_consumed": False}
        received = self.begin_receive(pid, receive_handle, capacity, deadline_ns, now_ns)
        if isinstance(received, ipc_v1_error):
            return {"error": received, "reply_consumed": True}
        if isinstance(received, dict) and "error" in received:
            return {"error": received, "reply_consumed": True}
        return {"received": received, "reply_consumed": True}


class ipc_v1_reference_model_test(unittest.TestCase):
    def setUp(self):
        self.model = reference_model()
        self.server_handle = self.model.create(10)
        self.client_handle = self.model.delegate(
            10, self.server_handle, 20, rights.call, 0xabc)

    def test_manifest_feature_model_is_not_product_support(self):
        query = reference_model.query_features()
        self.assertEqual(query["known"], ipc_v1_feature_known_mask)
        self.assertEqual(query["supported"], 0x3)
        self.assertEqual(query["limits"][0], ipc_v1_max_message_bytes)

    def test_both_sdk_profiles_share_an_unsupported_ipc_manifest_entry(self):
        entry = ipc_v1_manifest_entry()
        self.assertEqual(entry, {"abi_version": 1, "syscall": 88,
                                 "status": "registered_unsupported", "features": []})
        root = Path(__file__).resolve().parents[1]
        for builder in (root / "scripts/user_build.py",
                        root / "scripts/build_threading_sdk.py"):
            self.assertIn("ipc_v1_manifest_entry()", builder.read_text())

    def test_handle_owner_and_rights_are_authenticated(self):
        self.assertEqual(self.model.begin_receive(20, self.server_handle, 1, 0, 0),
                         ipc_v1_error.denied)
        self.assertEqual(self.model.submit_call(10, self.client_handle, 0, b"", 0, 0, 0),
                         ipc_v1_error.denied)

    def test_delegation_cannot_increase_rights(self):
        self.assertEqual(self.model.delegate(20, self.client_handle, 30,
                                             rights.manage, 0),
                         ipc_v1_error.denied)

    def test_per_process_endpoint_handle_quota(self):
        for index in range(ipc_v1_max_handles_per_process - 1):
            handle = self.model.delegate(10, self.server_handle, 20,
                                         rights.call, index + 1)
            self.assertIsInstance(handle, int)
        self.assertEqual(self.model.delegate(10, self.server_handle, 20,
                                             rights.call, 99),
                         ipc_v1_error.resources)

    def test_system_endpoint_quota_and_nonreused_handle(self):
        first = self.model.create(30)
        self.assertEqual(self.model.close(30, first), 0)
        second = self.model.create(31)
        self.assertGreater(second, first)
        for pid in range(40, 40 + ipc_v1_max_endpoints_system - 2):
            self.assertIsInstance(self.model.create(pid), int)
        self.assertEqual(self.model.create(999), ipc_v1_error.resources)

    def test_receive_first_rendezvous_preserves_badge_and_payload_snapshot(self):
        waiter = self.model.begin_receive(10, self.server_handle, 4, 100, 0)
        self.assertIn("pending", waiter)
        payload = bytearray(b"ping")
        call_id = self.model.submit_call(20, self.client_handle, 7, payload, 8, 100, 0)
        payload[0] = ord("X")
        received = self.model.poll_receive(waiter["pending"])
        self.assertEqual(received["call_id"], call_id)
        self.assertEqual(received["payload"], b"ping")
        self.assertEqual(received["badge"], 0xabc)

    def test_receive_buffer_too_small_does_not_consume(self):
        call_id = self.model.submit_call(20, self.client_handle, 1, b"long", 8, 100, 0)
        result = self.model.begin_receive(10, self.server_handle, 2, 0, 0)
        self.assertEqual(result["error"], ipc_v1_error.buffer_too_small)
        self.assertFalse(result["consumed"])
        result = self.model.begin_receive(10, self.server_handle, 4, 0, 0)
        self.assertEqual(result["call_id"], call_id)

    def test_reply_buffer_too_small_keeps_one_shot_token_live(self):
        received = self._deliver(b"q", reply_capacity=2)
        small = self.model.reply(10, received["reply_token"], 2, b"large")
        self.assertEqual(small["error"], ipc_v1_error.buffer_too_small)
        self.assertTrue(small["token_live"])
        reply = self.model.reply(10, received["reply_token"], 3, b"ok")
        self.assertEqual(reply["payload"], b"ok")
        self.assertEqual(self.model.reply(10, received["reply_token"], 3, b"again"),
                         ipc_v1_error.stale_token)

    def test_call_timeout_before_delivery_guarantees_no_delivery(self):
        call_id = self.model.submit_call(20, self.client_handle, 1, b"x", 2, 10, 0)
        self.model.expire(10)
        self.assertEqual(self.model.calls[call_id].state, phase.timed_out)
        self.assertEqual(self.model.begin_receive(10, self.server_handle, 2, 0, 10),
                         ipc_v1_error.would_block)

    def test_call_timeout_after_delivery_returns_result_unknown(self):
        received = self._deliver(b"x", deadline=10)
        self.model.expire(10)
        self.assertEqual(self.model.calls[received["call_id"]].state, phase.result_unknown)
        self.assertEqual(self.model.reply(10, received["reply_token"], 0, b"late"),
                         ipc_v1_error.stale_token)

    def test_close_distinguishes_queued_from_delivered_calls(self):
        queued = self.model.submit_call(20, self.client_handle, 1, b"q", 4, 100, 0)
        self.assertEqual(self.model.close(10, self.server_handle), 0)
        self.assertEqual(self.model.calls[queued].state, phase.closed)
        self.assertEqual(self.model.submit_call(20, self.client_handle, 1, b"q", 4, 100, 0),
                         ipc_v1_error.closed)

    def test_delivery_then_close_invalidates_reply_and_marks_unknown(self):
        received = self._deliver(b"q")
        self.assertEqual(self.model.close(10, self.server_handle), 0)
        self.assertEqual(self.model.calls[received["call_id"]].state, phase.result_unknown)
        self.assertEqual(self.model.reply(10, received["reply_token"], 0, b"late"),
                         ipc_v1_error.stale_token)

    def test_fifo_queue_and_depth_limit(self):
        ids = [self.model.submit_call(20, self.client_handle, n, b"", 1, 100, 0)
               for n in range(ipc_v1_max_queue_per_endpoint)]
        self.assertEqual(self.model.submit_call(20, self.client_handle, 99, b"", 1, 100, 0),
                         ipc_v1_error.queue_full)
        for call_id in ids:
            result = self.model.begin_receive(10, self.server_handle, 0, 0, 0)
            self.assertEqual(result["call_id"], call_id)

    def test_reply_token_quota_does_not_consume_next_call(self):
        for index in range(ipc_v1_max_reply_tokens_per_process):
            self.model.submit_call(20, self.client_handle, index, b"q", 8, 100, 0)
        received = []
        for _ in range(ipc_v1_max_reply_tokens_per_process):
            received.append(self.model.begin_receive(10, self.server_handle, 8, 0, 0))
        self.model.submit_call(20, self.client_handle, 99, b"q", 8, 100, 0)
        self.assertEqual(self.model.begin_receive(10, self.server_handle, 8, 0, 0),
                         ipc_v1_error.resources)
        self.model.reply(10, received[0]["reply_token"], 0, b"")
        next_received = self.model.begin_receive(10, self.server_handle, 8, 0, 0)
        self.assertEqual(next_received["label"], 99)

    def test_empty_and_maximum_messages_are_valid_but_max_plus_one_is_not(self):
        empty = self.model.submit_call(20, self.client_handle, 0, b"", 0, 100, 0)
        self.assertIsInstance(empty, int)
        maximum = self.model.submit_call(20, self.client_handle, 0,
                                         bytes(ipc_v1_max_message_bytes), 0, 100, 0)
        self.assertIsInstance(maximum, int)
        self.assertEqual(self.model.submit_call(20, self.client_handle, 0,
                                                bytes(ipc_v1_max_message_bytes + 1), 0, 100, 0),
                         ipc_v1_error.invalid_argument)

    def test_expired_deadline_still_observes_already_queued_message_first(self):
        call_id = self.model.submit_call(20, self.client_handle, 5, b"r", 0, 100, 0)
        result = self.model.begin_receive(10, self.server_handle, 1, 5, 10)
        self.assertEqual(result["call_id"], call_id)

    def test_reply_receive_reports_reply_success_when_receive_fails(self):
        first = self._deliver(b"first")
        result = self.model.reply_receive(10, first["reply_token"], 0, b"done",
                                         self.server_handle, 8, 0, 0)
        self.assertTrue(result["reply_consumed"])
        self.assertEqual(result["error"], ipc_v1_error.would_block)
        self.assertEqual(self.model.calls[first["call_id"]].state, phase.replied)

    def _deliver(self, payload, reply_capacity=8, deadline=100):
        call_id = self.model.submit_call(20, self.client_handle, 4, payload,
                                         reply_capacity, deadline, 0)
        return self.model.begin_receive(10, self.server_handle,
                                        ipc_v1_max_message_bytes, 0, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
