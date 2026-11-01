#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/temporal_semantics'))
from mock_producer import FrameRef, MockTemporalProducer


class TemporalSemanticsTest(unittest.TestCase):
    def setUp(self):
        self.now=100
        self.p=MockTemporalProducer(lambda:self.now)

    def test_time_domains_and_caption_authority(self):
        permit=self.p.permit_for_test({'metadata'},200)
        self.p.seek_for_test(1_000_000_000,'playing')
        snap=self.p.snapshot(permit)
        self.assertEqual(snap['observation'],{'domain':'simulated_monotonic_ns','value':100})
        self.assertEqual(snap['playback']['media_time_ns'],1_000_000_000)
        self.assertEqual(snap['captions']['status'],'RESTRICTED')
        self.assertEqual(snap['inference']['status'],'NOT_RUN')
        permit=self.p.permit_for_test({'metadata','captions'},200)
        caption=self.p.snapshot(permit)['captions']['items'][0]
        self.assertLessEqual(caption['start_media_ns'],1_000_000_000)
        self.assertGreater(caption['end_media_ns'],1_000_000_000)

    def test_on_demand_frame_and_budget(self):
        permit=self.p.permit_for_test({'metadata','frames'},200,1)
        refs=self.p.snapshot(permit)['frame_refs']
        self.assertEqual(self.p.read_synthetic_frame(permit,refs[0])['status'],'OK')
        self.assertEqual(self.p.read_synthetic_frame(permit,refs[1])['status'],'RESOURCE_LIMIT')

    def test_expiry_revocation_and_other_producer(self):
        permit=self.p.permit_for_test({'metadata','frames'},110,2)
        ref=self.p.snapshot(permit)['frame_refs'][0]
        other=MockTemporalProducer(lambda:self.now)
        self.assertEqual(other.snapshot(permit)['status'],'DENIED')
        self.p.revoke(permit)
        self.assertEqual(self.p.read_synthetic_frame(permit,ref)['status'],'DENIED')
        permit=self.p.permit_for_test({'metadata'},110)
        self.now=110
        self.assertEqual(self.p.snapshot(permit)['status'],'DENIED')

    def test_source_replacement_and_reference_validation(self):
        old=self.p.permit_for_test({'metadata','frames'},200,2)
        ref=self.p.snapshot(old)['frame_refs'][0]
        self.p.replace_source_for_test()
        self.assertEqual(self.p.read_synthetic_frame(old,ref)['status'],'DENIED')
        new=self.p.permit_for_test({'frames'},200,2)
        self.assertEqual(self.p.read_synthetic_frame(new,ref)['status'],'SOURCE_REPLACED')
        self.assertEqual(self.p.read_synthetic_frame(new,FrameRef(self.p.epoch,1,123))['status'],'UNKNOWN_REFERENCE')

    def test_invalid_scope_and_budget(self):
        with self.assertRaises(ValueError):self.p.permit_for_test({'audio'},200)
        with self.assertRaises(ValueError):self.p.permit_for_test({'frames'},200,9)
        with self.assertRaises(ValueError):self.p.seek_for_test(-1,'playing')


if __name__=='__main__':unittest.main()
