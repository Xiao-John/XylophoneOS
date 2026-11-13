"""Regression checks for stale port outputs on input and packaging failures."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class BuildFailures(unittest.TestCase):
    def test_failed_builds_remove_success_outputs(self):
        for name in ("lua", "zstd", "oniguruma"):
            spec = importlib.util.spec_from_file_location(
                name, ROOT / "src/ports" / name / "build.py")
            recipe = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(recipe)
            port = json.loads((recipe.HERE / "port.json").read_text())
            lock = json.loads((recipe.HERE / "source_lock.json").read_text())
            for failure in ("missing_sdk", "missing_archive", "bad_hash", "pack", "interrupt"):
                with self.subTest(port=name, failure=failure), tempfile.TemporaryDirectory() as temp:
                    out = Path(temp)
                    output = out / f"{port['package']['id']}-{lock['version']}.xpk"
                    receipt = out / "build_receipt.json"
                    staged = out / f"tree/usr/share/{name}/build_receipt.json"
                    staged.parent.mkdir(parents=True)
                    for path in (output, receipt, staged):
                        path.write_text("old success")
                    archive = out / "input.tar"
                    archive.write_bytes(b"invalid archive")
                    env = {"XOS_OUT": str(out)}
                    if failure != "missing_sdk":
                        env["XOS_SDK"] = str(out / "sdk")
                    if failure != "missing_archive":
                        env["XOS_SOURCE_ARCHIVE"] = str(archive)
                    with patch.dict(os.environ, env, clear=True):
                        if failure in ("pack", "interrupt"):
                            def fail(*args):
                                output.write_text("partial package")
                                staged.parent.mkdir(parents=True, exist_ok=True)
                                staged.write_text("new unpacked receipt")
                                raise KeyboardInterrupt() if failure == "interrupt" else RuntimeError("pack failed")
                            with patch.object(recipe, "build", side_effect=fail):
                                with self.assertRaises((RuntimeError, KeyboardInterrupt)):
                                    recipe.main()
                        else:
                            with self.assertRaises(SystemExit):
                                recipe.main()
                    self.assertFalse(output.exists())
                    self.assertFalse(receipt.exists())
                    self.assertFalse(staged.exists())


if __name__ == "__main__":
    unittest.main()
