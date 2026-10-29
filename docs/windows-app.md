# Use the Windows app

The portable Windows edition runs the workbench without installing Python, opening a terminal, creating an account or entering administrator credentials. It is intended for 64-bit Windows 10 and Windows 11, with a normal desktop browser available.

1. Download **Hypothesis-Lab-Windows.zip** from the project's release/download page.
2. Right-click the ZIP, choose **Extract All**, and choose a folder you can write to.
3. Open the extracted **Hypothesis-Lab** folder and double-click **Hypothesis Lab.exe**.
4. Your browser opens the workbench. Keep the small launcher window open while you work.

The app chooses an available local port automatically. **Open app** brings the workbench back in your browser. **Quit**, closing the launcher, or the workbench's **Stop app** button stops the local service. Closing a browser tab alone leaves the launcher running, so you can return to it.

Extract the whole archive. The executable needs its neighboring `runtime`, `hypothesis_lab` and `licenses` folders. Running only the executable from inside the ZIP, moving it away from those folders, or deleting runtime files can prevent startup. You can move or delete the complete extracted folder after quitting.

Each download is independent of the developer's computer and source checkout. The launcher finds its runtime and application beside its own executable, so the complete folder can be extracted or moved to another writable location. Deleting the original build/source folder does not affect copies already downloaded by other users or the assets hosted on GitHub. Keep any research or models you want to retain separately before deleting your own app folder.

This app is unsigned. Windows may show a reputation/security notice for a newly downloaded executable. Check that you obtained it from the intended project release and compare the published archive checksum when available. Code signing is not supplied by this release.

## What is included

The app bundles its own isolated CPython runtime, the local workbench, synthetic examples, static interface files and required runtime notices. The Windows release uses the official Python 3.14.10 embeddable runtime. It does not install Python into Windows or change file associations. It uses the Windows .NET Framework desktop components supplied with Windows for the small launcher window. Runtime source/library notices are kept in `licenses/`.

Rule research, imported datasets, core JSON model training/inference, feature tools, and requests to your own model endpoint run through the same application as the source edition. No model weights, heavy ML frameworks, third-party Python packages, package manager, SDK or local model server are bundled. An optional HTTP model endpoint must be operated or chosen by you. ONNX inference requires the advanced Python edition with its optional dependency; installing a random Python package on your computer does not alter the portable edition's isolated runtime.

The core workflow works offline with the synthetic examples. Optional providers and your model endpoints need the corresponding connection. Research is kept in the current session unless you choose to save or export it; saved settings and experiments use the local storage location described in the application's privacy/settings documentation. The app has no operator-hosted backend or telemetry.

## Build and verify this edition

Developers can build from source on 64-bit Windows using CPython 3.11+ and the Windows .NET Framework C# compiler. Supply the verified official Windows embeddable archive used for the release:

```console
python scripts/build_windows.py --runtime-zip path/to/python-3.14.10-embed-amd64.zip --output dist/Hypothesis-Lab-Windows.zip
```

This stages `dist/windows-app/Hypothesis-Lab/`, compiles the native launcher, keeps the official embedded standard-library ZIP, copies the current application and runtime licenses, and produces the downloadable archive. The builder itself downloads neither interpreter nor compiler. `--runtime` can select an existing complete CPython installation/embedded directory; omitting both runtime options uses `sys.base_prefix` and creates a compact source standard-library ZIP. Release automation uses the explicit upstream archive, verifies its pinned SHA-256, and records the runtime archive hash in the build manifest. Do not substitute a locally modified interpreter in an official release.

The build enforces an archive size below 25 MiB, inspects paths and CRCs, extracts into a separate temporary folder, and invokes the actual executable's offline smoke mode:

```console
python scripts/build_windows.py --verify dist/Hypothesis-Lab-Windows.zip
```

The check imports the app from the extracted folder using the bundled interpreter, verifies runtime isolation, serves the real local interface, runs an offline model and HTTP experiment, and performs authenticated HTTP shutdown. It does not open a browser or contact external APIs. The native executable also accepts `--smoke-test` for automation and `--no-browser` for launcher inspection. These developer options are not required for ordinary use.

Source archive packaging and this runnable Windows archive are separate artifacts. Other operating systems currently use the documented source edition. See implementation status for the platforms and launch paths actually exercised; no signing or universal Windows compatibility is implied by a successful local smoke check.
