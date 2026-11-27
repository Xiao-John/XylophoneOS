#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bind the Mobius package to a build recipe without receiver-local paths."""

from hashlib import sha256
from pathlib import PurePosixPath

from xypm_format import canonical, require

DIRECTORY_ROOTS = {"source", "build", "sdk", "widgets"}
FILE_ROOTS = {"profile", "gcc", "g++", "ar", "ranlib"}


def absolute_path(value):
    require(isinstance(value, str), "Expected a Mobius build path string")
    path = PurePosixPath(value)
    require(path.is_absolute() and str(path) == value and ".." not in path.parts,
            "Expected a canonical absolute Mobius build path")
    return path


def packaged_build_binding(receipt, original_digest):
    if "relocation_paths" not in receipt:
        return {"build_receipt_sha256": original_digest}

    locations = receipt["relocation_paths"]
    require(isinstance(locations, dict) and "widgets_kit_manifest_sha256" in receipt
            and set(locations) == DIRECTORY_ROOTS | FILE_ROOTS,
            "Unexpected Mobius build recipe roots")
    roots = [(absolute_path(path), name) for name, path in locations.items()]
    require(len({path for path, _ in roots}) == len(roots), "Overlapping Mobius build recipe roots")
    roots.sort(key=lambda item: len(item[0].parts), reverse=True)

    def portable_path(value):
        path = absolute_path(value)
        for root, name in roots:
            if path == root:
                return f"${{{name}}}"
            if name in DIRECTORY_ROOTS and path.is_relative_to(root):
                return f"${{{name}}}/{path.relative_to(root).as_posix()}"
        raise ValueError("Mobius build path has no recipe root")

    def portable_argument(argument):
        if argument.startswith("/"):
            return portable_path(argument)
        flag, separator, value = argument.partition("=")
        if separator and value.startswith("/"):
            return flag + separator + portable_path(value)
        return argument

    recipe = dict(receipt)
    del recipe["relocation_paths"]
    recipe["commands"] = [[portable_argument(argument) for argument in command]
                          for command in receipt["commands"]]
    recipe["inputs"] = {portable_path(path): digest for path, digest in receipt["inputs"].items()}
    return {"build_recipe_sha256": sha256(canonical(recipe)).hexdigest()}
