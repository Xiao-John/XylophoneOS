# SPDX-License-Identifier: Apache-2.0
import idna

name = "ドメイン.テスト"
encoded = idna.encode(name).decode("ascii")
assert encoded == "xn--eckwd4c7c.xn--zckzah", encoded
assert idna.decode(encoded) == name

try:
    idna.encode("abc☃.com")
except idna.InvalidCodepoint:
    pass
else:
    raise AssertionError("disallowed codepoint accepted")

print("PY3_A3_IDNA_OK", encoded)
