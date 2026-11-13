"""Check bc input cleanup and the SDK gate without a cross compiler."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from xos_app import tree_receipt
from xypm_format import PackageError


class BcBuildValidation(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("bc_build", ROOT / "src/ports/bc/build.py")
        self.recipe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.recipe)

    def test_missing_inputs_clear_previous_outputs(self):
        for missing in ("XOS_SDK", "XOS_SOURCE_ARCHIVE"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                outputs = [out / "thirdparty.bc-1.08.2.xpk", out / "build_receipt.json",
                           out / "tree/usr/share/bc/build_receipt.json"]
                for output in outputs:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_text("old success")
                env = {"XOS_OUT": temp, "XOS_SDK": temp, "XOS_SOURCE_ARCHIVE": temp}
                del env[missing]
                with patch.dict(os.environ, env, clear=True):
                    with self.assertRaisesRegex(SystemExit, missing + " is required"):
                        self.recipe.main()
                self.assertTrue(all(not output.exists() for output in outputs))

    def test_sdk_gate_precedes_toolchain(self):
        for case in ("unregistered", "registered", "wrong_abi", "missing_library"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                here = root / "src/ports/bc"
                here.mkdir(parents=True)
                sdk = root / "sdk"
                sdk.mkdir()
                (sdk / "manifest.json").write_text(json.dumps({
                    "abi": 2 if case == "wrong_abi" else 1,
                    "target": "x86_64-elf", "build_id": "synthetic"}))
                for name in ("crt0_posix.o", "user.ld", "lib/libxos.a", "lib/libc.a",
                             "lib/libm.a", "lib/libxos_loader.a", "cpp/lib/libgcc.a"):
                    path = sdk / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"synthetic fixture")
                if case == "missing_library":
                    (sdk / "lib/libc.a").unlink()
                profile_path = Path("config/package/xos_x86_64_static_single_b2_v1.json")
                profile = json.loads((ROOT / profile_path).read_text())
                profile["sdk_tree_sha256"] = [] if case == "unregistered" else [tree_receipt(sdk)[0]]
                (root / profile_path).parent.mkdir(parents=True)
                (root / profile_path).write_text(json.dumps(profile))
                for name in ("port.json", "source_lock.json"):
                    (here / name).write_bytes((self.recipe.HERE / name).read_bytes())
                archive = root / "source.tar"
                archive.write_bytes(b"synthetic archive")
                lock = json.loads((here / "source_lock.json").read_text())
                lock["sha256"] = self.recipe.sha256(archive)
                (here / "source_lock.json").write_text(json.dumps(lock))
                env = {"XOS_OUT": str(root / "out"), "XOS_SDK": str(sdk),
                       "XOS_SOURCE_ARCHIVE": str(archive), "XOS_SDK_UNREGISTERED_OK": "1"}
                with patch.dict(os.environ, env, clear=True), patch.object(self.recipe, "HERE", here), \
                        patch.object(self.recipe.shutil, "which", return_value=None) as compiler:
                    if case == "registered":
                        with self.assertRaisesRegex(SystemExit, "must be on PATH"):
                            self.recipe.main()
                        self.assertTrue(compiler.called)
                    else:
                        message = {"unregistered": "not registered", "wrong_abi": "unsupported SDK",
                                   "missing_library": "SDK missing lib/libc.a"}[case]
                        with self.assertRaisesRegex(PackageError, message):
                            self.recipe.main()
                        compiler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
