# SPDX-License-Identifier: Apache-2.0
import _hashlib
import hashlib
import sys

assert '_hashlib' in sys.builtin_module_names
assert '_ssl' not in sys.builtin_module_names
assert '_socket' not in sys.builtin_module_names
assert hashlib.sha256.__module__ == '_hashlib'
assert hashlib.sha256(b'abc').hexdigest() == (
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
assert _hashlib.hmac_digest(b'key', b'The quick brown fox jumps over the lazy dog', 'sha256').hex() == (
    'f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8')
assert hashlib.pbkdf2_hmac('sha256', b'password', b'salt', 2, 32).hex() == (
    'ae4d0c95af6b46d32d0adff928f06dd02a303f8ef3c251dfd6e2d85a95474c43')
assert hashlib.scrypt(b'', salt=b'', n=16, r=1, p=1).hex() == (
    '77d6576238657b203b19ca42c18a0497f16b4844e3074ae8dfdffa3fede21442f'
    'cd0069ded0948f8326a753a0fc81f17e8d3e0fb2e0d3628cf35e20c38d18906')
try:
    _hashlib.new('xos-unsupported-digest')
except ValueError:
    pass
else:
    raise AssertionError('unsupported OpenSSL digest was accepted')

print('CPYTHON_G4_OPENSSL_HASHLIB_PASS sha256 hmac pbkdf2 scrypt reject', flush=True)
