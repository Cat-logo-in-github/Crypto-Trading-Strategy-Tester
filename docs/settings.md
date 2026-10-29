# Local settings, privacy and optional credentials

The core needs no key, account or hosted service. The public Pages site never asks for credentials. The working application runs on localhost; provider and model requests originate from the user's computer. There is no app-operator endpoint receiving the user's query, data, model weights or keys.

## Session-first experiments

New UI runs are held in process memory by default. The shared **Save this experiment on this computer** checkbox sets `persist_local`; leave it unchecked for a session-only record. The buffer retains up to 20 recent runs and evicts older records when its estimated JSON size exceeds 50 MB, while retaining the latest run. Ending the process removes those in-memory records.

Explicitly saved runs and exported files can contain imported datasets, configurations, results and supported numeric model parameters. The user chooses those durable copies. **Include explicitly saved local runs** in Experiment history makes local saved records available for View/Rerun. Runtime-only session records are distinct from those files.

Saved state uses `HYPOTHESIS_LAB_HOME`, otherwise `%LOCALAPPDATA%/HypothesisLab` on Windows or `~/.local/share/hypothesis-lab` elsewhere. Keep private state and exports out of source control and release archives. Deleting local state is the user's file-management choice; export anything needed before doing so.

## Source keys

Data discovery can fetch public sources without a key where supported. For an authenticated custom HTTPS API, enter the provider's documented URL/header configuration and your own masked session key. Private shop or merch systems require the owner's authorized data/API; the app cannot obtain that permission or invent a free public equivalent.

Source keys are separate request arguments, not dataset columns, experiment specifications or export fields. Successful source fetches clear the UI's temporary key field. The adapter does not follow redirects with credentials and rejects credential-bearing URLs. Keys are sent only to the selected provider; quotas, fees and provider-side retention remain that provider's responsibility.

## User-model and LLM connections

A model/LLM endpoint defaults to localhost. Its optional masked key stays in this page/process workflow and is excluded from experiment exports. The app does not write it into a `.env` file, Pages assets or the source ZIP. Clear its input or close the local page when finished; browser form memory and process memory are different from a permanent credential store.

Remote model use requires an explicit HTTPS opt-in. That provider can receive selected queries/features and may charge for requests. Choose request and token budgets before running. A localhost model still needs user-installed weights and sufficient hardware; no model weights or heavy SDKs are bundled.

Numeric JSON models stay in session unless the user saves/exports a run. A local ONNX path references files the user owns; those weights are not copied into the application ZIP. An exported path/reference does not make the model available on another computer. See [model inputs](model-inputs.md).

## Separate legacy Alpha Vantage key test

The original optional Alpha Vantage settings view retains an explicit **save/update** workflow. It is the exception to session-only source/model key inputs: checking its consent control and saving creates a local credential file. No source-file or `.env` editing is required. Its test requests an end-of-day quote from Alpha Vantage's fixed HTTPS endpoint and uses the provider's quota; it is not a real-time trading connection.

The settings status shows storage location and whether a key exists without returning its value. **Remove** erases that saved credential file. On Windows, the implementation uses current-user DPAPI; if protection is unavailable, it fails rather than silently saving plaintext. On other systems, the owner-restricted local file is not encrypted and is not an operating-system secret manager. Backups or a compromised local account can expose saved state.

This explicit legacy save should not be confused with the generic source/model key fields. Those do not automatically use or create the credential file. Browser local storage is not used as a substitute secret store. For the current executed platform evidence, see [implementation status](../IMPLEMENTATION_STATUS.md).
