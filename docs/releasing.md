# Publish the app, Pages and source release

There are two downloads: **Hypothesis-Lab-Windows.zip** for Windows users who do not want a Python setup, and **hypothesis-lab.zip** for source/development. The public Pages site is their documentation/download hub. Research runs on each user's computer; Pages does not host the Python engine or collect research data.

After the source and release assets are published to GitHub, this build computer and its local folders are no longer needed. Pages serves files hosted on GitHub, its download buttons use GitHub Releases, and Actions rebuilds from repository files plus the official runtime download. Documentation is included in the repository and published Pages site. The local preview address is only a temporary preview, never the public download host.

## Repository owner: publish through GitHub's website

No local Git command is required for this path.

1. Extract the source ZIP, open its `hypothesis-lab` folder and upload its **contents** to the repository using **Add file > Upload files**. Include `.github/`, `src/`, `scripts/`, `site/`, `docs/`, tests and the root project files. Do not upload only the enclosing folder or place the application under another nested `hypothesis-lab/` directory. Never upload your private experiment state, keys, environments or model weights.
2. Commit the source to the intended default branch. The supplied workflows use `main`; if the repository has another branch name, adapt their branch filters. Open **Actions** and confirm workflows are enabled. The core/source and Windows packaging workflows then have the repository files they need.
3. Under **Settings > Pages > Build and deployment > Source**, select **GitHub Actions**. The Pages workflow builds the landing/docs site after a push to `main`, or from its **Run workflow** control. The first deployment may need the repository's Pages environment approval if one has been configured by its owner.
4. Open **Releases > Draft a new release**. Choose/create a tag such as **v0.4.0**, target the uploaded branch, write the release notes and publish it. Use an ordinary published release if the site's `releases/latest` links should point to it; drafts and prereleases do not supply that same latest-release path.
5. Wait for **Downloadable app and source release** in Actions to finish. It builds the source ZIP and the portable Windows app, verifies them, and attaches the stable ZIP names and SHA-256 checksum assets to the versioned release. Check the release's **Assets** list before sharing the download links.

The source ZIP must include `.github/workflows` at the repository root for these steps to work. A local build, uploaded source or successful Pages deployment does not itself mean the Windows release asset is already published. This task configures the workflows; it does not publish a remote site or release on the owner's behalf.

### If publishing shows Skipped

A normal branch push builds the two archives as Actions artifacts. The **publish** job deliberately skips those pushes; it attaches public download assets only for a version tag beginning with `v` (for example `v0.4.0`) or a published release. Upload the extracted source contents, not the unopened ZIP as a repository file. After the checks pass, publish a normal release from the current corrected commit. If an earlier tag points at faulty source, create a new version tag for the corrected commit rather than rerunning the old tag. Failed prerequisite build/test jobs also prevent publication. The Pages button works only after the normal release contains `Hypothesis-Lab-Windows.zip` under Assets.

## Visitors: three steps

1. Download **Hypothesis-Lab-Windows.zip** from the published release or the Pages download button.
2. Extract the whole archive into a folder.
3. Open **Hypothesis Lab.exe** inside `Hypothesis-Lab`.

The package includes a private portable Python runtime. Visitors do not install Python, open a terminal, use administrator access or edit `.env` files. Keep the runtime/app files together and the small launcher window open. **Quit** in the launcher or **Stop app** in the browser stops the local service.

Stable latest-release URLs:

- [Windows app](https://github.com/Cat-logo-in-github/Crypto-Trading-Strategy-Tester/releases/latest/download/Hypothesis-Lab-Windows.zip)
- [Developer source ZIP](https://github.com/Cat-logo-in-github/Crypto-Trading-Strategy-Tester/releases/latest/download/hypothesis-lab.zip)

These links become usable after a corresponding normal release has been published and its assets attached. The portable Windows edition includes standard-library research, numeric JSON models and user-operated model endpoints. Optional native ONNX use belongs to the advanced Python edition, with its separately installed runtime; model weights are not bundled in either release.

## What the workflows actually do

| Workflow | Scope |
| --- | --- |
| Core checks | Offline tests, lint/format/type checks, Python distribution build, samples, static docs, source ZIP and clean extraction on the configured OS/Python matrix |
| Optional native ONNX job | Installs the optional runtime and graph-test packages, requires their imports and executes a self-contained graph test without silently treating missing dependencies as a pass |
| GitHub Pages | Builds `dist/site/`, uploads supported Pages artifacts and deploys using minimal Pages/id-token permissions; manual deployment is available |
| Downloadable app and source release | Builds/verifies source and Windows artifacts; publishes ZIPs and checksum assets on a version tag or published release |

The Windows job obtains the official x64 CPython **3.14.10 embeddable ZIP** from `python.org` and verifies the pinned SHA-256 before packaging it. Its private isolated interpreter starts the application rather than depending on system Python. The archive includes runtime/application license notices and a file manifest. SDKs, development environments, user data and model weights are excluded.

The portable Windows archive has a **25 MiB** release budget. The separate source ZIP has a **20 MB** archive budget and **10 MB** maximum included source-file budget. These limits keep model weights and installed dependency trees out of release artifacts; users keep large local models or inference services separately.

## Local developer checks and builds

Run from the source repository root. Development-tool installation may need network access; core tests and bundled examples do not require external APIs.

```console
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m build
python scripts/build_site.py
python scripts/package.py
```

`build_site.py` writes `dist/site/` from bundled assets and escaped Markdown documentation. Relative links support repository subpaths. The landing specimen remains labeled as illustrative, not a market result. Never insert private keys or research exports into site assets.

The source packager writes one `hypothesis-lab/` root with sorted entries, stable timestamps and permission fields. Its whitelist retains source, synthetic fixtures, tests, examples, docs, workflows, scripts and approved legacy references. It excludes Git history, caches, environments, credentials, user/downloaded datasets, logs and large model assets. It rejects unsafe/alias paths, symbolic links, Windows reserved names and known token/private-key signatures. An automated scanner is not proof that arbitrary text contains no secret; review added content before publishing.

Extract into a new empty directory and run the documented workflow there:

```console
python scripts/package.py --verify dist/hypothesis-lab.zip --extract dist/clean-check
```

Inside `dist/clean-check/hypothesis-lab`, install in a fresh environment, run the offline samples/tests and build the static site. Start the local app and verify shutdown. This checks the delivered paths rather than only a development checkout.

## Reproduce the Windows build on Windows

Use 64-bit CPython 3.11+ on the build machine. The workflow pins this official runtime archive:

```text
https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip
SHA-256: 90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159
```

Obtain and verify that archive, then run:

```console
python scripts/build_windows.py --runtime-zip work/python-3.14.10-embed-amd64.zip --output dist/Hypothesis-Lab-Windows.zip
python scripts/build_windows.py --verify dist/Hypothesis-Lab-Windows.zip
```

The builder validates the portable archive and executes the actual launcher smoke path on Windows. Its smoke check requires the private interpreter and exercises the local app without provider APIs. For a final manual check, extract the download, open **Hypothesis Lab.exe**, use the browser workbench and select **Quit**. The executable is an unsigned portable launcher; no code-signing claim is made.

Actual local results, skipped optional tests, archive hashes and final clean-copy evidence are recorded in the delivered verification report and [implementation status](../IMPLEMENTATION_STATUS.md). Configured remote workflows are not reported as successful remote executions until they actually run.
