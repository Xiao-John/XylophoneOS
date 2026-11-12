# SPDX-License-Identifier: Apache-2.0
"""Check the real guest-output predicate; this does not execute guest binutils."""
import ast
from pathlib import Path
import re
import time
import unittest

repo_root = Path(__file__).resolve().parents[1]
source_text = repo_root / "tests/binutils_stress.py"
run_node = next(node for node in ast.walk(ast.parse(source_text.read_text()))
           if isinstance(node, ast.FunctionDef) and node.name == "run")
run_code = compile(ast.Module(body=[run_node], type_ignores=[]), str(source_text), "exec")


class guest_exit_tests(unittest.TestCase):
    def runner(self, actual):
        output = f"[wait] pid=42 kind=exited code={actual}\nxsh> ".encode()
        context = {
            "time": time, "re": re, "guest": object(), "baseline": (100, 1, 0),
            "report": {"commands": []},
            "command": lambda *args, **kwargs: output,
            "resources": lambda guest: (100, 1, 0),
        }
        exec(run_code, context)
        return context["run"]

    def test_negative_case_rejects_zero(self):
        with self.assertRaises(AssertionError):
            self.runner(0)("ld truncated.o", code=None)

    def test_negative_case_accepts_nonzero(self):
        for actual in (1, 2, -1):
            with self.subTest(actual=actual):
                self.runner(actual)("ld truncated.o", code=None)

    def test_explicit_exit_remains_exact(self):
        self.runner(42)("app.elf", code=42)
        with self.assertRaises(AssertionError):
            self.runner(0)("app.elf", code=42)


if __name__ == "__main__":
    unittest.main()
