"""Build and validate a deterministic, explicitly whitelisted source release."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "hypothesis-lab"
MAX_ARCHIVE_BYTES = 20_000_000
MAX_SOURCE_FILE_BYTES = 10_000_000
TOP_FILES = {
    "MANIFEST.in",
    "README.md",
    "LICENSE",
    "NOTICE.md",
    "AUDIT.md",
    "IMPLEMENTATION_STATUS.md",
    "pyproject.toml",
    ".gitignore",
}
DENIED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "local-state",
    "logs",
    "raw",
    "processed",
    "weights",
    "checkpoints",
    "user-models",
    "downloads",
    "artifacts",
}
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{24,}\b"),
)
WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


def safe_components(name: str) -> bool:
    """Reject path aliases before PurePosixPath can normalize their spelling."""
    components = name.split("/")
    return all(
        part not in {"", ".", ".."}
        and part == part.rstrip(" .")
        and part.split(".", 1)[0].casefold() not in WINDOWS_RESERVED
        and not any(ord(character) < 32 or character in '<>"|?*' for character in part)
        for part in components
    )


def allowed(path: PurePosixPath) -> bool:
    """A deny rule always wins, then only known release paths are included."""
    if any(
        part.casefold() in DENIED_PARTS or part.casefold().endswith(".egg-info")
        for part in path.parts
    ):
        return False
    if path.name.casefold().startswith(".env") and path.name.casefold() != ".env.example":
        return False
    if path.suffix.lower() in {
        ".pyc",
        ".pyo",
        ".log",
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        ".onnx",
        ".gguf",
        ".safetensors",
        ".pt",
        ".pth",
        ".bin",
        ".pkl",
        ".pickle",
        ".joblib",
    }:
        return False
    if len(path.parts) == 1:
        return path.name in TOP_FILES
    first, suffix = path.parts[0], path.suffix.lower()
    if first == "legacy":
        return suffix in {".py", ".md", ".png"} or path.name in {
            "requirements.txt",
            ".env.example",
        }
    if first == ".github":
        return len(path.parts) == 3 and path.parts[1] == "workflows" and suffix in {".yml", ".yaml"}
    if first == "src":
        return path == PurePosixPath("src/hypothesis_lab/fixtures/README.md") or (
            path.parts[1] == "hypothesis_lab"
            and suffix
            in {
                ".py",
                ".csv",
                ".json",
                ".html",
                ".css",
                ".js",
                ".svg",
                ".png",
            }
        )
    if first == "scripts" and len(path.parts) > 2 and path.parts[1] == "runtime-licenses":
        return suffix == ".txt"
    if first == "scripts" and suffix == ".cs":
        return True
    if first in {"tests", "scripts"}:
        return suffix == ".py"
    if first == "examples":
        return suffix in {".py", ".json", ".md", ".csv"}
    if first == "docs":
        return (
            suffix in {".md", ".png", ".svg"}
            or path.as_posix() == "docs/public-strategy-results.json"
        )
    if first == "site":
        return suffix in {".html", ".css", ".js", ".svg", ".png", ".md"}
    return False


def check_secret(data: bytes, name: str) -> None:
    if any(pattern.search(data) for pattern in SECRET_PATTERNS):
        raise ValueError(f"Possible credential/private key in {name}; release refused")


def source_files(root: Path = ROOT) -> list[tuple[PurePosixPath, Path]]:
    if root.is_symlink():
        raise ValueError("Source root must not be a symbolic link")
    root = root.resolve(strict=True)
    found = []
    for directory, folders, filenames in os.walk(root, followlinks=False):
        folders[:] = [
            name
            for name in folders
            if name.casefold() not in DENIED_PARTS
            and not name.casefold().endswith(".egg-info")
            and not (Path(directory) / name).is_symlink()
            and (Path(directory) / name).resolve().is_relative_to(root)
        ]
        for name in filenames:
            file = Path(directory) / name
            if file.is_symlink() or not file.resolve().is_relative_to(root):
                continue
            relative = PurePosixPath(file.relative_to(root).as_posix())
            if not safe_components(str(relative)):
                raise ValueError(f"Unsafe source path: {relative}")
            if allowed(relative):
                found.append((relative, file))
    return sorted(found, key=lambda item: str(item[0]))


def verify_archive(archive: Path, extract_to: Path | None = None) -> dict[str, int | str]:
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError(
            "Source ZIP exceeds the 20 MB release budget; keep model weights, dependencies and user data outside the release"
        )
    with zipfile.ZipFile(archive) as release:
        names = release.namelist()
        if not names or len(names) != len({name.casefold() for name in names}):
            raise ValueError("Archive is empty or has duplicate entries")
        if (
            len(names) > 20_000
            or sum(entry.file_size for entry in release.infolist()) > 500_000_000
        ):
            raise ValueError("Archive exceeds release validation size limits")
        for entry in release.infolist():
            if entry.file_size > MAX_SOURCE_FILE_BYTES:
                raise ValueError("A bundled source file exceeds the 10 MB budget")
            name = entry.filename
            path = PurePosixPath(name)
            if (
                "\\" in name
                or not safe_components(name)
                or entry.orig_filename != name
                or path.is_absolute()
                or ".." in path.parts
                or len(path.parts) < 2
                or path.parts[0] != PREFIX
                or ":" in name
                or not allowed(PurePosixPath(*path.parts[1:]))
            ):
                raise ValueError(f"Unsafe or unwanted archive path: {name}")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Archive contains a symbolic link")
            check_secret(release.read(entry), name)
        required = {f"{PREFIX}/{name}" for name in TOP_FILES if name != ".gitignore"}
        required.update(
            {
                f"{PREFIX}/src/hypothesis_lab/__main__.py",
                f"{PREFIX}/src/hypothesis_lab/fixtures/market.csv",
            }
        )
        if not required.issubset(names):
            raise ValueError(f"Required release files are missing: {sorted(required - set(names))}")
        bad = release.testzip()
        if bad:
            raise ValueError(f"Archive CRC check failed: {bad}")
        if extract_to is not None:
            target = extract_to.resolve()
            if target.exists() and any(target.iterdir()):
                raise ValueError("Extraction destination must be new or empty")
            target.mkdir(parents=True, exist_ok=True)
            for entry in release.infolist():
                output = target.joinpath(*PurePosixPath(entry.filename).parts).resolve()
                if not output.is_relative_to(target):
                    raise ValueError("Extraction target escaped the destination")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(release.read(entry))
    return {
        "archive": str(archive.resolve()),
        "files": len(names),
        "bytes": archive.stat().st_size,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }


def build_archive(destination: Path) -> dict[str, int | str]:
    files = source_files()
    destination.parent.mkdir(parents=True, exist_ok=True)
    for relative, file in files:
        if file.stat().st_size > MAX_SOURCE_FILE_BYTES:
            raise ValueError(f"Source file exceeds the 10 MB release budget: {relative}")
        check_secret(file.read_bytes(), str(relative))
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as release:
        for relative, file in files:
            entry = zipfile.ZipInfo(f"{PREFIX}/{relative}", date_time=(2026, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            release.writestr(entry, file.read_bytes(), compresslevel=9)
    return verify_archive(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "hypothesis-lab.zip")
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--extract", type=Path)
    args = parser.parse_args()
    if args.extract and not args.verify:
        parser.error("--extract requires --verify")
    result = (
        verify_archive(args.verify, args.extract) if args.verify else build_archive(args.output)
    )
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
