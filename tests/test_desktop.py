"""Portable edition tests that do not require a compiler or installed Python extras."""

import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from hypothesis_lab.desktop_smoke import run_smoke

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "windows_builder", ROOT / "scripts" / "build_windows.py"
)
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class DesktopTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "work" / "test-desktop"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="desktop-", dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def test_portable_standard_library_omits_installed_packages_and_developer_tools(self):
        with tempfile.TemporaryDirectory(dir=self.directory) as temporary:
            runtime = Path(temporary)
            wanted = ["encodings/__init__.py", "json/__init__.py", "urllib/request.py"]
            unwanted = [
                "site-packages/numpy/__init__.py",
                "test/test_socket.py",
                "email/test/t.py",
                "tkinter/__init__.py",
                "idlelib/__main__.py",
                "ensurepip/__init__.py",
                "venv/__init__.py",
                "__pycache__/x.py",
                "turtledemo/demo.py",
            ]
            for name in wanted + unwanted:
                target = runtime / "Lib" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("# fixture", encoding="utf-8")
            actual = {
                relative.as_posix() for relative, _ in BUILDER.standard_library_files(runtime)
            }
            self.assertEqual(actual, set(wanted))

    def test_portable_zip_entries_have_stable_order_timestamps_and_permissions(self):
        with tempfile.TemporaryDirectory(dir=self.directory) as temporary:
            first, second = (Path(temporary) / name for name in ("one.zip", "two.zip"))
            files = [("Hypothesis-Lab/b.txt", b"b"), ("Hypothesis-Lab/a.txt", b"a")]
            BUILDER.write_zip(first, files)
            BUILDER.write_zip(second, files)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), sorted(archive.namelist()))
                self.assertTrue(
                    all(item.date_time == BUILDER.FIXED_TIME for item in archive.infolist())
                )

    def test_portable_verifier_rejects_traversal_and_bundled_model_weights(self):
        with tempfile.TemporaryDirectory(dir=self.directory) as temporary:
            archive = Path(temporary) / "bad.zip"
            for name in [
                "Hypothesis-Lab/../escape.py",
                "Hypothesis-Lab/model.gguf",
                "Hypothesis-Lab/runtime/site-packages/numpy/__init__.py",
                "Hypothesis-Lab/hypothesis_lab/__pycache__/x.pyc",
            ]:
                BUILDER.write_zip(archive, [(name, b"fixture")])
                with self.subTest(name=name), self.assertRaises(ValueError):
                    BUILDER.verify_archive(archive, smoke=False)

    def test_embedded_runtime_extraction_rejects_aliases_devices_and_path_traversal(self):
        archive = self.directory / "runtime.zip"
        destination = self.directory / "runtime"
        for name in ["../escape.dll", "sub/python.exe", "C:/escape.dll", "NUL.dll", "name. "]:
            BUILDER.write_zip(archive, [(name, b"fixture")])
            with self.subTest(name=name), self.assertRaises(ValueError):
                BUILDER.unpack_runtime_archive(archive, destination)
            self.assertFalse(destination.exists())

    def test_embedded_runtime_extraction_preserves_verified_input_bytes(self):
        archive = self.directory / "runtime.zip"
        destination = self.directory / "runtime"
        BUILDER.write_zip(archive, [("python314.zip", b"stdlib"), ("LICENSE.txt", b"license")])
        BUILDER.unpack_runtime_archive(archive, destination)
        self.assertEqual((destination / "python314.zip").read_bytes(), b"stdlib")
        self.assertEqual((destination / "LICENSE.txt").read_bytes(), b"license")

    def test_real_offline_desktop_smoke_serves_runs_and_stops_without_saved_state(self):
        with patch.dict("os.environ", {"HYPOTHESIS_LAB_PORTABLE": ""}):
            report = run_smoke(self.directory)
        self.assertEqual(report["status"], "passed")
        self.assertIn("authenticated shutdown", report["checks"])
        self.assertFalse(report["portable"])


if __name__ == "__main__":
    unittest.main()
