# SPDX-License-Identifier: Apache-2.0
"""Run the files slot adapter against a real independent host authority."""

import argparse
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from pumpkin_generation_authority import generation_authority, generation_error, generation_mark, publish_result


slot_bytes = 4608
realm = bytes.fromhex("51704432" + "00" * 12)
actions = {name: i for i, name in enumerate(("load", "provision", "enroll", "authenticate", "revoke"))}
ok, denied, not_found, io_error, outcome_unknown = 0, 2, 3, 8, 9
loaded_record, absent_record, record_error = 0, 1, 2
publication_result = {
    publish_result.committed: 0, publish_result.conflict: 1,
    publish_result.unchanged: 2, publish_result.outcome_unknown: 3,
}


class mark_value(ct.Structure):
    _fields_ = [("realm", ct.c_uint8 * 16), ("revision", ct.c_uint64),
                ("length", ct.c_size_t), ("checksum", ct.c_uint8 * 32)]

    def mark(self):
        if self.revision == 0:
            assert not any(bytes(self))
            return None
        return generation_mark(bytes(self.realm), self.revision, self.length, bytes(self.checksum))

    def set_mark(self, mark):
        self.realm[:] = mark.realm
        self.revision = mark.revision
        self.length = mark.length
        self.checksum[:] = mark.checksum


slot_callback = ct.CFUNCTYPE(ct.c_bool, ct.c_uint32, ct.c_void_p, ct.c_size_t)
read_callback = ct.CFUNCTYPE(ct.c_uint32, ct.POINTER(mark_value))
publish_callback = ct.CFUNCTYPE(ct.c_uint32, ct.POINTER(mark_value), ct.POINTER(mark_value))


class host_calls(ct.Structure):
    _fields_ = [("read_slot", slot_callback), ("write_slot", slot_callback),
                ("read_mark", read_callback), ("publish_mark", publish_callback)]


def run_child(library, image, authority_root, action, fault):
    provider = generation_authority(authority_root, realm)
    file = os.open(image, os.O_RDWR)
    events = []
    failures = []

    def guarded(callback, failure):
        def call(*args):
            try:
                return callback(*args)
            except Exception as error:
                failures.append(f"{callback.__name__}: {error}")
                return failure
        return call

    def read_slot(slot, output, size):
        assert slot in (0, 1) and size == slot_bytes
        events.append(f"read-slot:{slot}")
        data = os.pread(file, size, slot * size)
        if len(data) != size:
            return False
        ct.memmove(output, data, size)
        return True

    def write_slot(slot, data, size):
        assert slot in (0, 1) and size == slot_bytes
        frame = ct.string_at(data, size)
        offset = slot * size
        if os.pwrite(file, frame, offset) != size:
            return False
        os.fsync(file)
        if os.pread(file, size, offset) != frame:
            return False
        events.append(f"verified-slot:{slot}")
        if fault == "readback-damage":
            assert os.pwrite(file, b"!", offset) == 1
            os.fsync(file)
        return True

    def read_mark(output):
        events.append("read-generation")
        try:
            mark = provider.read()
        except generation_error:
            return record_error
        if mark is None:
            return absent_record
        output.contents.set_mark(mark)
        return loaded_record

    def publish_mark(expected, next_value):
        result = provider.publish(expected.contents.mark(), next_value.contents.mark())
        events.append(f"publish:{result.name}")
        if fault == "lost-reply" and result == publish_result.committed:
            result = publish_result.outcome_unknown
        return publication_result[result]

    try:
        callbacks = host_calls(slot_callback(guarded(read_slot, False)), slot_callback(guarded(write_slot, False)),
                               read_callback(guarded(read_mark, record_error)),
                               publish_callback(guarded(publish_mark, publication_result[publish_result.outcome_unknown])))
        execute = ct.CDLL(str(library)).pumpkin_anchored_store_fixture
        execute.argtypes = [ct.POINTER(host_calls), ct.c_uint32]
        execute.restype = ct.c_uint32
        result = execute(ct.byref(callbacks), actions[action])
        assert not failures, failures
        print(json.dumps((result, events)))
    finally:
        os.close(file)


def exercise(library, directory):
    authority_root = directory / "independent"
    authority_root.mkdir(mode=0o700)
    authority = generation_authority(authority_root, realm)
    authority.provision()
    image = directory / "slot-image"

    def write_image(contents):
        with image.open("wb") as stream:
            assert stream.write(contents) == 2 * slot_bytes
            stream.flush()
            os.fsync(stream.fileno())

    def invoke(action, expected, fault="none"):
        result = subprocess.check_output([sys.executable, "-B", __file__, "--fixture", str(library),
                                          str(image), str(authority_root), action, fault], text=True, timeout=20)
        status, events = json.loads(result)
        assert status == expected, (action, status, expected, events)
        return events

    write_image(bytes(2 * slot_bytes))
    assert invoke("load", not_found) == ["read-generation"]
    assert invoke("provision", ok) == ["read-generation", "verified-slot:0", "read-slot:0", "publish:committed"]
    assert authority.read().revision == 1
    assert invoke("enroll", ok)[-3:] == ["verified-slot:1", "read-slot:1", "publish:committed"]
    assert authority.read().revision == 2
    assert invoke("authenticate", ok) == ["read-generation", "read-slot:1"]
    old_image = image.read_bytes()
    print("PASS provision, enrollment and fresh-process authentication through selected files slots")

    assert invoke("revoke", io_error, "readback-damage")[-2:] == ["verified-slot:0", "read-slot:0"]
    assert authority.read().revision == 2
    invoke("authenticate", ok)
    print("PASS failed stage readback preserves independent selection and authentication")

    assert invoke("revoke", outcome_unknown, "lost-reply")[-3:] == ["verified-slot:0", "read-slot:0", "publish:committed"]
    assert authority.read().revision == 3
    assert invoke("authenticate", denied) == ["read-generation", "read-slot:0"]
    current_image = image.read_bytes()
    print("PASS confirmed revoke after lost reply, core stop and fresh-process authentication denial")

    write_image(old_image)
    assert invoke("authenticate", io_error) == ["read-generation", "read-slot:0"]
    assert invoke("provision", outcome_unknown) == ["read-generation", "read-slot:0"]
    assert authority.read().revision == 3 and image.read_bytes() == old_image
    write_image(bytes(slot_bytes) + current_image[slot_bytes:])
    assert invoke("load", io_error) == ["read-generation", "read-slot:0"]
    print("PASS stale or missing selected slot fails without fallback or automatic provisioning")

    different = bytearray(current_image)
    payload_end = 16 + int.from_bytes(different[8:12], "little")
    different[16 + 48 + 4] = ord("x")  # first byte of the disabled test account name
    different[payload_end - 32:payload_end] = hashlib.sha256(different[16:payload_end - 32]).digest()
    write_image(different)
    assert invoke("load", io_error) == ["read-generation", "read-slot:0"]
    write_image(current_image[:slot_bytes] + b"!" + bytes(slot_bytes - 1))
    assert invoke("authenticate", denied) == ["read-generation", "read-slot:0"]
    print("PASS same-revision different digest fails and unselected damage cannot select another generation")

    record = authority_root / realm.hex() / "generation"
    record.unlink()
    assert invoke("load", io_error) == ["read-generation"]
    assert invoke("provision", outcome_unknown) == ["read-generation"]
    assert not record.exists()
    print("PASS missing trusted provider record fails without touching slots")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-cxx", help="also compile with the XOS freestanding compiler")
    args = parser.parse_args()
    common = ["-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror", "-I", root / "src/shared/include",
              "-I", root / "src/user/include", "-I", root / "src/user"]
    module = root / "src/user/pumpkin"
    sources = [module / name for name in ("account_store.cpp", "service_core.cpp", "snapshot_publication.cpp",
                                          "anchored_files_store.cpp")]
    with tempfile.TemporaryDirectory(prefix="pumpkin_anchored_") as scratch:
        directory = Path(scratch)
        library = directory / "anchored_files_store.so"
        fixture = root / "tests/fixtures/pumpkin/anchored_files_store_host.cpp"
        subprocess.run([os.environ.get("CXX", "c++"), *common, "-shared", "-fPIC", *sources, fixture, "-o", library],
                       check=True, timeout=60)
        exercise(library, directory)
        if args.target_cxx:
            flags = ["-ffreestanding", "-fno-exceptions", "-fno-rtti", "-nostdinc++", "-mno-red-zone"]
            for source in (*sources, module / "files_slot_client.cpp", module / "disk_test_store.cpp"):
                subprocess.run([args.target_cxx, *common, *flags, "-c", source,
                                "-o", directory / (source.stem + ".o")], check=True, timeout=60)
            print("PASS freestanding XOS adapter and native files client object compilation")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--fixture"]:
        run_child(*sys.argv[2:])
    else:
        main()
