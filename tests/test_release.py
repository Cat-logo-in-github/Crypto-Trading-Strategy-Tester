"""Release allowlist, safe ZIP extraction, deterministic packaging and static links."""

import importlib.util
import tempfile
import unittest
import warnings
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    specification = importlib.util.spec_from_file_location(
        f"lab_{name}", ROOT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


package = script("package")
site = script("build_site")


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        self.targets.extend(value for key, value in attrs if key in {"href", "src"} and value)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / "work" / "test-release"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="release-", dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def archive(self, extra=(), *, required=True):
        entries = []
        if required:
            entries.extend(
                (f"{package.PREFIX}/{name}", b"release source")
                for name in package.TOP_FILES
                if name != ".gitignore"
            )
            entries += [
                (f"{package.PREFIX}/src/hypothesis_lab/__main__.py", b"# entry point"),
                (
                    f"{package.PREFIX}/src/hypothesis_lab/fixtures/market.csv",
                    b"timestamp,open,high,low,close\n",
                ),
            ]
        entries.extend(extra)
        archive = self.directory / "test.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(archive, "w") as release:
                for name, value in entries:
                    if isinstance(name, str):
                        # ZipInfo sanitizes backslashes on Windows. Preserve the
                        # raw spelling so malformed-name tests exercise the ZIP.
                        entry = zipfile.ZipInfo("safe-name")
                        entry.filename = name
                        entry.orig_filename = name
                    else:
                        entry = name
                    release.writestr(entry, value)
        return archive

    def test_allowlist_rejects_local_data_secrets_caches_and_environments(self):
        accepted = (
            "README.md",
            "src/hypothesis_lab/engine.py",
            "src/hypothesis_lab/fixtures/market.csv",
            "src/hypothesis_lab/fixtures/README.md",
            "legacy/requirements.txt",
            "legacy/bitcoin-trading-bot/requirements.txt",
            "legacy/research-wing/analysis/config/.env.example",
            "tests/test_core.py",
            "docs/quickstart.md",
            ".github/workflows/ci.yml",
        )
        denied = (
            ".env",
            ".git/config",
            ".venv/pyvenv.cfg",
            "node_modules/a.js",
            "local-state/credential.json",
            "work/dataset.csv",
            "src/hypothesis_lab/.env.local",
            "src/hypothesis_lab/__pycache__/engine.pyc",
            "legacy/research-wing/analysis/data/raw/user.csv",
            "legacy/research-wing/analysis/data/processed/user.json",
            "logs/bot.log",
            "src/hypothesis_lab/private.key",
            "dist/hypothesis-lab.zip",
        )
        for name in accepted:
            with self.subTest(name=name):
                self.assertTrue(package.allowed(PurePosixPath(name)))
        for name in denied:
            with self.subTest(name=name):
                self.assertFalse(package.allowed(PurePosixPath(name)))

    def test_credential_scanner_rejects_private_keys_and_token_shapes(self):
        samples = (
            b"-----BEGIN " + b"PRIVATE KEY-----",
            b"AKIA" + b"A" * 16,
            b"ghp_" + b"A" * 36,
            b"github_pat_" + b"A" * 40,
            b"sk-" + b"a" * 30,
        )
        for value in samples:
            with self.subTest(prefix=value[:8]), self.assertRaises(ValueError):
                package.check_secret(value, "fixture.txt")
        package.check_secret(b"Enter your own optional API key in local settings.", "docs.md")

    def test_archive_rejects_traversal_absolute_paths_local_files_and_duplicate_entries(self):
        for path in (
            "hypothesis-lab/../escape.py",
            "/hypothesis-lab/src/hypothesis_lab/escape.py",
            "hypothesis-lab\\src\\hypothesis_lab\\escape.py",
            "hypothesis-lab/src/hypothesis_lab/C:escape.py",
            "hypothesis-lab/src/hypothesis_lab//empty.py",
            "hypothesis-lab/src/hypothesis_lab/./dot.py",
            "hypothesis-lab/src/hypothesis_lab/nul\x00.py",
            "hypothesis-lab/.git/config",
            "hypothesis-lab/src/hypothesis_lab/.env",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                package.verify_archive(self.archive([(path, b"data")]))
        duplicate = "hypothesis-lab/src/hypothesis_lab/duplicate.py"
        with self.assertRaises(ValueError):
            package.verify_archive(self.archive([(duplicate, b"one"), (duplicate, b"two")]))
        with self.assertRaises(ValueError):
            package.verify_archive(self.archive(required=False))

    def test_archive_rejects_windows_alias_collisions_and_trailing_dot_space(self):
        entries = [
            ("hypothesis-lab/src/hypothesis_lab/case.py", b"one"),
            ("hypothesis-lab/src/hypothesis_lab/CASE.py", b"two"),
        ]
        with self.assertRaises(ValueError):
            package.verify_archive(self.archive(entries))
        for path in (
            "hypothesis-lab/src/hypothesis_lab/alias. /evil.py",
            "hypothesis-lab/src/hypothesis_lab/alias./evil.py",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                package.verify_archive(self.archive([(path, b"data")]))

        for device in ("CON", "PRN", "AUX", "NUL", "COM1", "LPT9"):
            with self.subTest(device=device), self.assertRaises(ValueError):
                package.verify_archive(
                    self.archive([(f"hypothesis-lab/src/hypothesis_lab/{device}.py", b"data")])
                )

    def test_archive_rejects_symlinks_and_embedded_credentials(self):
        link = zipfile.ZipInfo("hypothesis-lab/src/hypothesis_lab/link.py")
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        with self.assertRaises(ValueError):
            package.verify_archive(self.archive([(link, b"../../private")]))
        with self.assertRaises(ValueError):
            package.verify_archive(
                self.archive(
                    [
                        (
                            "hypothesis-lab/src/hypothesis_lab/settings.py",
                            b"token = '" + b"sk-" + b"a" * 30 + b"'",
                        )
                    ]
                )
            )

    def test_safe_extract_checks_required_files_and_never_overwrites_nonempty_directory(self):
        archive = self.archive()
        target = self.directory / "clean"
        evidence = package.verify_archive(archive, target)
        self.assertGreater(evidence["files"], 5)
        self.assertEqual((target / "hypothesis-lab" / "README.md").read_bytes(), b"release source")
        with self.assertRaises(ValueError):
            package.verify_archive(archive, target)
        with self.assertRaises(ValueError):
            package.verify_archive(
                self.archive(required=False, extra=[("hypothesis-lab/README.md", b"partial")])
            )

    def test_real_source_release_build_is_deterministic_and_excludes_state(self):
        first, second = self.directory / "first.zip", self.directory / "second.zip"
        package.build_archive(first)
        package.build_archive(second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        package.verify_archive(first, self.directory / "extracted")
        with zipfile.ZipFile(first) as release:
            names = release.namelist()
        self.assertIn("hypothesis-lab/src/hypothesis_lab/static/index.html", names)
        self.assertIn("hypothesis-lab/tests/test_release.py", names)
        self.assertIn("hypothesis-lab/legacy/requirements.txt", names)
        self.assertIn("hypothesis-lab/legacy/research-wing/analysis/config/.env.example", names)
        self.assertFalse(
            any(
                "/work/" in name
                or "/__pycache__/" in name
                or (
                    PurePosixPath(name).name.startswith(".env")
                    and PurePosixPath(name).name != ".env.example"
                )
                for name in names
            )
        )

    def test_static_build_internal_links_work_under_a_repository_subpath(self):
        destination = self.directory / "site"
        self.assertGreaterEqual(site.build(destination), 10)
        for page in destination.rglob("*.html"):
            parser = Links()
            parser.feed(page.read_text(encoding="utf-8"))
            for target in parser.targets:
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                with self.subTest(page=page.relative_to(destination), link=target):
                    self.assertFalse(
                        parsed.path.startswith("/"),
                        "Root-relative URLs break GitHub repository subpaths",
                    )
                    resolved = (page.parent / unquote(parsed.path)).resolve()
                    self.assertTrue(resolved.is_relative_to(destination.resolve()))
                    self.assertTrue(resolved.is_file(), f"Broken internal link: {target}")
        self.assertTrue((destination / ".nojekyll").is_file())

    def test_static_renderer_escapes_html_and_rejects_script_links(self):
        rendered = site.markdown(
            "# Test\n\n<script>alert(1)</script>\n\n[unsafe](javascript:alert) [safe](https://example.com)\n"
        )
        self.assertNotIn("<script>", rendered)
        self.assertNotIn('href="javascript:', rendered)
        self.assertIn('href="https://example.com"', rendered)
        self.assertIn("&lt;script&gt;", rendered)


if __name__ == "__main__":
    unittest.main()
