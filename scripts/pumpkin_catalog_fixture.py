# SPDX-License-Identifier: Apache-2.0
"""Emit explicit trusted-test catalog inputs; this is not a distribution verifier."""
import hashlib
import json
from pathlib import Path
import re


def emit(source, destination):
    data = Path(source).read_bytes()
    value = json.loads(data)
    if (not isinstance(value, dict) or value.keys() != {"format", "sdk_sha256", "roots"} or
            value["format"] != "xos-pumpkin-catalog-fixture-v1" or
            not isinstance(value["sdk_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["sdk_sha256"]) or
            not isinstance(value["roots"], list) or len(value["roots"]) != 2):
        raise ValueError("invalid explicit catalog fixture")

    def path(name):
        if (not isinstance(name, str) or len(name) >= 128 or not name.startswith("/") or
                any(not re.fullmatch(r"[A-Za-z0-9_+.-]+", part) or part in (".", "..") for part in name[1:].split("/"))):
            raise ValueError("catalog fixture path must be canonical bounded ASCII")
        return json.dumps(name)

    def bytes_initializer(digest):
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("catalog fixture requires SHA-256")
        return "{" + ",".join("0x" + digest[index:index + 2] for index in range(0, 64, 2)) + "}"

    roots = []
    identifiers = set()
    for root in value["roots"]:
        if (not isinstance(root, dict) or root.keys() != {"id", "sha256", "manifest", "main"} or
                type(root["id"]) is not int or not 0 < root["id"] < 2**64 or root["id"] in identifiers):
            raise ValueError("catalog fixture requires two unique generation identities")
        identifiers.add(root["id"])
        roots.append("{" + str(root["id"]) + "ULL," + bytes_initializer(root["sha256"]) + "," +
                     path(root["manifest"]) + "}")
        path(root["main"])
    header = ("// SPDX-License-Identifier: Apache-2.0\n#pragma once\n#include <xos/catalog_abi.hpp>\n"
              "inline constexpr xos::catalog::snapshot pumpkin_catalog_fixture{2,0,1,0,0," +
              bytes_initializer(value["sdk_sha256"]) + ",{" + ",".join(roots) + "}};\n"
              "inline constexpr const char* pumpkin_catalog_main_paths[]{" +
              ",".join(path(root["main"]) for root in value["roots"]) + "};\n")
    Path(destination).write_text(header)
    return {"pumpkin_catalog_fixture": {**value, "input_sha256": hashlib.sha256(data).hexdigest(),
                                       "header_sha256": hashlib.sha256(header.encode()).hexdigest()}}
