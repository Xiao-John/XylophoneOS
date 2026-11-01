#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host-only synthetic temporal observations. No decoder, model or security boundary."""
from dataclasses import dataclass
from hashlib import sha256
from typing import Callable, FrozenSet


@dataclass(frozen=True)
class FrameRef:
    source_epoch: int
    frame_id: int
    presentation_ns: int  # media timeline, not a system clock


@dataclass
class TestPermit:
    # A local simulation of decisions, not a transferable or secure grant.
    owner: object
    source_epoch: int
    scopes: FrozenSet[str]
    expires_ns: int  # simulated observation clock
    remaining_frames: int
    revoked: bool = False


class MockTemporalProducer:
    SCOPES = frozenset({'metadata', 'captions', 'frames'})

    def __init__(self, observation_clock: Callable[[], int]):
        self.clock = observation_clock
        self._identity = object()
        self.epoch = 1
        self.version = 1
        self.state = 'paused'
        self.media_ns = 0
        # These are synthetic bytes, not decoded images.
        self.frames = {1: (0, b'synthetic-frame-1'), 2: (2_000_000_000, b'synthetic-frame-2')}
        self.caption = (500_000_000, 1_500_000_000, 'Synthetic caption')

    def permit_for_test(self, scopes, expires_ns: int, frame_budget: int = 0) -> TestPermit:
        scopes = frozenset(scopes)
        if not scopes <= self.SCOPES or expires_ns < 0 or frame_budget < 0 or frame_budget > 8:
            raise ValueError('invalid simulated permit')
        return TestPermit(self._identity, self.epoch, scopes, expires_ns, frame_budget)

    def revoke(self, permit: TestPermit) -> None:
        permit.revoked = True

    def _allowed(self, permit: TestPermit, scope: str) -> bool:
        return (permit.owner is self._identity and permit.source_epoch == self.epoch and
                not permit.revoked and self.clock() < permit.expires_ns and scope in permit.scopes)

    def seek_for_test(self, media_ns: int, state: str) -> None:
        if media_ns < 0 or state not in ('playing', 'paused'):
            raise ValueError('invalid simulated playback')
        self.media_ns, self.state = media_ns, state
        self.version += 1

    def replace_source_for_test(self) -> None:
        self.epoch += 1
        self.version += 1
        self.media_ns, self.state = 0, 'paused'

    def snapshot(self, permit: TestPermit) -> dict:
        if not self._allowed(permit, 'metadata'):
            return {'status': 'DENIED'}
        result = {
            'status': 'OK', 'source_epoch': self.epoch, 'version': self.version,
            'observation': {'domain': 'simulated_monotonic_ns', 'value': self.clock()},
            'playback': {'state': self.state, 'media_time_ns': self.media_ns},
            'audio': {'status': 'NOT_SIMULATED'},
            'inference': {'status': 'NOT_RUN'},
        }
        if self._allowed(permit, 'captions'):
            start, end, text = self.caption
            result['captions'] = {'status': 'OK', 'items': [{'start_media_ns': start,
                'end_media_ns': end, 'text': text, 'provenance': 'synthetic-producer'}]}
        else:
            result['captions'] = {'status': 'RESTRICTED'}
        if self._allowed(permit, 'frames'):
            result['frame_refs'] = [FrameRef(self.epoch, frame_id, value[0])
                                    for frame_id, value in self.frames.items()]
        else:
            result['frames'] = {'status': 'RESTRICTED'}
        return result

    def read_synthetic_frame(self, permit: TestPermit, ref: FrameRef) -> dict:
        if not self._allowed(permit, 'frames'):
            return {'status': 'DENIED'}
        if ref.source_epoch != self.epoch:
            return {'status': 'SOURCE_REPLACED'}
        value = self.frames.get(ref.frame_id)
        if value is None or value[0] != ref.presentation_ns:
            return {'status': 'UNKNOWN_REFERENCE'}
        if permit.remaining_frames <= 0:
            return {'status': 'RESOURCE_LIMIT'}
        permit.remaining_frames -= 1
        return {'status': 'OK', 'provenance': 'synthetic-bytes-not-a-decoded-frame',
                'bytes': value[1], 'sha256': sha256(value[1]).hexdigest()}
