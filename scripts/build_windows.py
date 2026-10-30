"""Build a small Windows portable app from this source and the current CPython runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "Hypothesis-Lab"
EXE_NAME = "Hypothesis Lab.exe"
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
SKIP_STDLIB = {
    "site-packages",
    "test",
    "tests",
    "tkinter",
    "idlelib",
    "ensurepip",
    "venv",
    "__pycache__",
    "turtledemo",
}
APP_SUFFIXES = {".py", ".csv", ".json", ".html", ".css", ".js", ".svg", ".png", ".md"}
WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


def safe_component(name: str) -> bool:
    return (
        name not in {"", ".", ".."}
        and name == name.rstrip(" .")
        and name.split(".", 1)[0].casefold() not in WINDOWS_RESERVED
        and not any(ord(character) < 32 or character in '<>"|?*' for character in name)
    )


def standard_library_files(python_home: Path) -> list[tuple[Path, Path]]:
    library = python_home / "Lib"
    files = []
    for directory, folders, names in os.walk(library, followlinks=False):
        folders[:] = [
            name
            for name in folders
            if name.casefold() not in SKIP_STDLIB and not (Path(directory) / name).is_symlink()
        ]
        for name in names:
            path = Path(directory) / name
            if path.suffix == ".py" and not path.is_symlink():
                files.append((path.relative_to(library), path))
    if not any(
        str(relative).replace("\\", "/") == "encodings/__init__.py" for relative, _ in files
    ):
        raise ValueError("The Python runtime does not contain its source standard library")
    return sorted(files, key=lambda item: item[0].as_posix())


def write_zip(destination: Path, files: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files):
            entry = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data, compresslevel=9)


def copy_runtime(python_home: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    core_dlls = [
        file
        for file in python_home.glob("python*.dll")
        if re.fullmatch(r"python\d{2,3}\.dll", file.name)
    ]
    if len(core_dlls) != 1:
        raise ValueError("Select one complete CPython runtime with a versioned interpreter DLL")
    tag = core_dlls[0].stem
    required = ["python.exe", core_dlls[0].name, "python3.dll", "LICENSE.txt"]
    for name in required:
        file = python_home / name
        if not file.is_file():
            raise ValueError(f"Python runtime is missing {name}")
        shutil.copyfile(file, destination / name)
    for name in ["pythonw.exe", *[file.name for file in python_home.glob("vcruntime*.dll")]]:
        file = python_home / name
        if file.is_file():
            shutil.copyfile(file, destination / name)
    for extensions in (python_home, python_home / "DLLs"):
        if not extensions.is_dir():
            continue
        for file in extensions.iterdir():
            lower = file.name.casefold()
            if file.suffix.casefold() not in {".pyd", ".dll"}:
                continue
            if lower.startswith(("_test", "_ctypes_test", "_tkinter", "tcl", "tk")):
                continue
            if file.is_file() and not file.is_symlink():
                shutil.copyfile(file, destination / file.name)
    # Some managed Python builds add an adjacent public-CA policy file to ssl.py.
    # Keep that module and its data together on disk; native SSL cannot open a
    # certificate through a zipimport path. Preserve the policy unchanged.
    public_ca_policy = python_home / "Lib" / "codex-rejected-cas.pem"
    if public_ca_policy.is_file():
        shutil.copyfile(python_home / "Lib" / "ssl.py", destination / "ssl.py")
        shutil.copyfile(public_ca_policy, destination / public_ca_policy.name)
    if (python_home / "Lib").is_dir():
        write_zip(
            destination / "stdlib.zip",
            [
                (relative.as_posix(), file.read_bytes())
                for relative, file in standard_library_files(python_home)
                if not (public_ca_policy.is_file() and relative.as_posix() == "ssl.py")
            ],
        )
    else:
        embedded_stdlib = python_home / f"{tag}.zip"
        if not embedded_stdlib.is_file():
            raise ValueError("Embedded runtime is missing its standard-library ZIP")
        shutil.copyfile(embedded_stdlib, destination / "stdlib.zip")
    # A ._pth file isolates sys.path and disables site initialization and PYTHONPATH.
    (destination / f"{tag}._pth").write_text("stdlib.zip\n.\n..\n", encoding="ascii")


def unpack_runtime_archive(archive: Path, destination: Path) -> None:
    """Accept an upstream flat embeddable ZIP without trusting extraction paths."""
    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        if not names or len(names) != len({name.casefold() for name in names}):
            raise ValueError("Embedded runtime contains duplicate paths")
        if sum(entry.file_size for entry in source.infolist()) > 100 * 1024 * 1024:
            raise ValueError("Embedded runtime exceeds the supported size")
        for entry in source.infolist():
            name = entry.filename
            if (
                name != entry.orig_filename
                or "/" in name
                or "\\" in name
                or ":" in name
                or not safe_component(name)
                or (entry.external_attr >> 16) & 0o170000 == 0o120000
                or Path(name).suffix.casefold()
                not in {".exe", ".dll", ".pyd", ".zip", ".txt", "._pth", ".cat"}
            ):
                raise ValueError(f"Unexpected embedded-runtime entry: {name}")
        if source.testzip():
            raise ValueError("Embedded-runtime ZIP failed CRC verification")
        destination.mkdir(parents=True, exist_ok=True)
        for entry in source.infolist():
            (destination / entry.filename).write_bytes(source.read(entry))


def runtime_information(runtime: Path) -> dict:
    command = [
        str(runtime / "python.exe"),
        "-B",
        "-c",
        "import json,sys,struct,ssl; print(json.dumps({'python':sys.version.split()[0],"
        "'bits':struct.calcsize('P')*8,'isolated':bool(sys.flags.isolated),"
        "'openssl':ssl.OPENSSL_VERSION}))",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    if result.returncode:
        raise RuntimeError("Bundled Python did not start:\n" + result.stdout + result.stderr)
    info = json.loads(result.stdout)
    version = tuple(int(value) for value in info["python"].split(".")[:2])
    if version < (3, 11) or info["bits"] != 64 or not info["isolated"]:
        raise ValueError("Portable runtime must be isolated 64-bit CPython 3.11 or newer")
    return info


def copy_application(destination: Path) -> None:
    source = ROOT / "src" / "hypothesis_lab"
    for file in source.rglob("*"):
        if not file.is_file() or file.is_symlink():
            continue
        relative = file.relative_to(source)
        if "__pycache__" in relative.parts or file.suffix.casefold() not in APP_SUFFIXES:
            continue
        if len(relative.parts) > 1 and relative.parts[0] not in {"fixtures", "static"}:
            continue
        target = destination / "hypothesis_lab" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)


def compile_launcher(destination: Path) -> None:
    framework = (
        Path(os.environ.get("WINDIR", r"C:\Windows"))
        / "Microsoft.NET"
        / "Framework64"
        / "v4.0.30319"
    )
    compiler = framework / "csc.exe"
    if not compiler.is_file():
        raise ValueError("The Windows .NET Framework C# compiler was not found")
    command = [
        str(compiler),
        "/nologo",
        "/target:winexe",
        "/platform:x64",
        "/optimize+",
        "/debug-",
        "/reference:System.Windows.Forms.dll",
        "/reference:System.Drawing.dll",
        "/reference:System.Web.Extensions.dll",
        f"/out:{destination / EXE_NAME}",
        str(ROOT / "scripts" / "windows_launcher.cs"),
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("Windows launcher compilation failed:\n" + result.stdout + result.stderr)


def portable_files(folder: Path) -> list[tuple[str, bytes]]:
    return [
        (f"{APP_NAME}/{file.relative_to(folder).as_posix()}", file.read_bytes())
        for file in sorted(folder.rglob("*"))
        if file.is_file() and not file.is_symlink()
    ]


def verify_archive(archive: Path, *, smoke: bool = True) -> dict:
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Portable archive exceeds the 25 MiB release limit")
    with zipfile.ZipFile(archive) as release:
        names = release.namelist()
        if not names or len(names) != len({name.casefold() for name in names}):
            raise ValueError("Portable archive is empty or contains duplicate paths")
        if sum(entry.file_size for entry in release.infolist()) > 200 * 1024 * 1024:
            raise ValueError("Portable archive expands beyond its supported size")
        for entry in release.infolist():
            path = PurePosixPath(entry.filename)
            parts = entry.filename.split("/")
            if (
                entry.filename != entry.orig_filename
                or "\\" in entry.filename
                or ":" in entry.filename
                or path.is_absolute()
                or parts[0] != APP_NAME
                or any(not safe_component(part) for part in parts)
                or any(
                    part.casefold()
                    in {"site-packages", "__pycache__", "node_modules", ".git", ".venv"}
                    for part in parts
                )
                or any(part.casefold().startswith(".env") for part in parts)
                or path.suffix.casefold()
                in {".pyc", ".pyo", ".log", ".onnx", ".gguf", ".safetensors", ".pt", ".pth"}
                or (entry.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError(f"Unwanted portable archive entry: {entry.filename}")
        required = {
            f"{APP_NAME}/{EXE_NAME}",
            f"{APP_NAME}/runtime/python.exe",
            f"{APP_NAME}/runtime/stdlib.zip",
            f"{APP_NAME}/licenses/Python-LICENSE.txt",
            f"{APP_NAME}/hypothesis_lab/__main__.py",
            f"{APP_NAME}/hypothesis_lab/desktop_smoke.py",
            f"{APP_NAME}/hypothesis_lab/static/index.html",
            f"{APP_NAME}/hypothesis_lab/fixtures/market.csv",
        }
        if not required.issubset(names) or release.testzip():
            raise ValueError("Portable archive is missing required files or failed CRC validation")
        report = {
            "archive": str(archive.resolve()),
            "bytes": archive.stat().st_size,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "files": len(names),
        }
        if smoke:
            if os.name != "nt":
                raise ValueError("The actual Windows launcher smoke check requires Windows")
            temporary_parent = ROOT / "work" / "desktop-check"
            temporary_parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="portable-", dir=temporary_parent) as temporary:
                target = Path(temporary).resolve()
                for entry in release.infolist():
                    output = target.joinpath(*PurePosixPath(entry.filename).parts).resolve()
                    if not output.is_relative_to(target):
                        raise ValueError("Portable extraction escaped its destination")
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(release.read(entry))
                executable = target / APP_NAME / EXE_NAME
                environment = dict(os.environ)
                environment["HYPOTHESIS_LAB_HOME"] = str(target / "state")
                environment["HYPOTHESIS_LAB_SMOKE_HOME"] = str(target / "smoke")
                environment["PYTHONPATH"] = str(ROOT / "src")  # Must be ignored by ._pth isolation.
                result = subprocess.run(
                    [str(executable), "--smoke-test"],
                    cwd=target,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=100,
                    check=False,
                )
                if result.returncode:
                    raise RuntimeError(
                        "Portable launcher smoke failed:\n" + result.stdout + result.stderr
                    )
                report["smoke"] = json.loads(result.stdout)
                if not report["smoke"].get("portable"):
                    raise AssertionError("Smoke check did not use the portable interpreter")
    return report


def build(output: Path, runtime: Path | None = None, runtime_zip: Path | None = None) -> dict:
    if os.name != "nt" or struct.calcsize("P") != 8 or sys.version_info[:2] < (3, 11):
        raise ValueError("Build the Windows app with 64-bit CPython 3.11+ on Windows")
    if runtime is not None and runtime_zip is not None:
        raise ValueError("Select a runtime directory or embedded ZIP, not both")
    python_home = runtime.resolve() if runtime is not None else Path(sys.base_prefix).resolve()
    staging_parent = ROOT / "dist" / "windows-app"
    stage = staging_parent / APP_NAME
    if not stage.resolve().is_relative_to(ROOT.resolve() / "dist"):
        raise ValueError("Portable staging path escaped the repository build directory")
    staging_parent.mkdir(parents=True, exist_ok=True)
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    if runtime_zip is not None:
        temporary_parent = ROOT / "work" / "runtime-source"
        temporary_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="embedded-", dir=temporary_parent) as temporary:
            unpack_runtime_archive(runtime_zip, Path(temporary))
            copy_runtime(Path(temporary), stage / "runtime")
    else:
        copy_runtime(python_home, stage / "runtime")
    runtime_info = runtime_information(stage / "runtime")
    copy_application(stage)
    compile_launcher(stage)
    licenses = stage / "licenses"
    licenses.mkdir()
    shutil.copyfile(stage / "runtime" / "LICENSE.txt", licenses / "Python-LICENSE.txt")
    for name in ("LICENSE", "NOTICE.md"):
        shutil.copyfile(ROOT / name, licenses / name)
    third_party = ROOT / "scripts" / "runtime-licenses"
    if third_party.is_dir():
        for file in third_party.glob("*.txt"):
            shutil.copyfile(file, licenses / file.name)
    (stage / "START HERE.txt").write_text(
        "Hypothesis Lab for Windows 10/11 (64-bit)\n\n"
        "1. Extract the whole ZIP into a folder.\n"
        "2. Double-click Hypothesis Lab.exe. The app opens in your browser.\n"
        "3. Keep the small launcher window open. Click Quit or Stop app to finish.\n\n"
        "No Python installation, account, terminal command or administrator access is required.\n"
        "This is an unsigned portable app; Windows may display a reputation/security notice.\n"
        "Research is session-only unless you choose to save or export it. Optional services\n"
        "receive requests only when you choose to connect. No model weights are bundled.\n"
        "ONNX needs the advanced Python edition; JSON models and your own HTTP model endpoint work here.\n"
        "Licenses and runtime notices are in licenses/. Keep the runtime and app folders together.\n",
        encoding="utf-8",
    )
    manifest = {
        "application": "Hypothesis Lab",
        "version": "0.4.0",
        "platform": "Windows x64",
        "python": runtime_info["python"],
        "openssl": runtime_info["openssl"],
        "runtime_source": "supplied embedded archive"
        if runtime_zip
        else "supplied installation"
        if runtime
        else "build interpreter installation",
        "runtime_archive_sha256": hashlib.sha256(runtime_zip.read_bytes()).hexdigest()
        if runtime_zip
        else None,
        "portable_runtime": True,
        "runtime_changes": "CPython binaries retained; supplied embedded stdlib archive retained or source stdlib zipped; test/Tcl/pip/development packages omitted; isolated search path configured.",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in portable_files(stage)},
    }
    (stage / "build-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    write_zip(output, portable_files(stage))
    report = verify_archive(output)
    report["staged_app"] = str(stage)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "Hypothesis-Lab-Windows.zip")
    parser.add_argument("--verify", type=Path)
    parser.add_argument(
        "--runtime", type=Path, help="Use this CPython installation/embedded directory"
    )
    parser.add_argument(
        "--runtime-zip", type=Path, help="Use a verified upstream Windows embeddable ZIP"
    )
    args = parser.parse_args()
    report = (
        verify_archive(args.verify)
        if args.verify
        else build(args.output, args.runtime, args.runtime_zip)
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
