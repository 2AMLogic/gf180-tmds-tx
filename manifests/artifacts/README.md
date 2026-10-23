# manifests/artifacts

Committed manifests for evidence whose bytes live in the artifact store, not in
git. One manifest per simulation run:
`<bench>-<record-id>.manifest.json`, cited from the run's
`sim/<bench>/records/<record-id>.md` (**Links**).

- **What a run commits**: this manifest and the summary record, which lists
  name, size and sha256 per object. The raw per-corner logs are not committed.
- **Entry names** are the paths the logs would have had on disk:
  `sim/<bench>/corners/<record-id>/<corner-id>.log`. `sim/check_records.py`
  runs the corner-id grammar and the Operating point rate cross-check over
  these names.
- **URIs** are logical `artifact:<key>` only; no bucket, endpoint or broker URL
  appears anywhere in the repo. `scripts/check_artifact_manifests.py` (lint
  step 8) rejects anything else, rejects a malformed entry, and fails if a
  stored object's bytes are also committed.
- **Append-only**: a manifest is never edited or deleted; a re-run mints a new
  record-id and manifest.
- **Writing**: `python3 sim/run_corners.py <bench>` stages logs under the
  git-ignored `sim/.work/.stage/` and stores them with `klt artifact put`. It
  needs `KLT_ARTIFACT_BROKER` set and a `klt` with `artifact put`, and exits
  nonzero before simulating otherwise. There is no flag that commits the bytes
  instead.
- **Checking against the store**: `klt artifact verify <manifest>` (needs the
  broker, so CI does not run it).

Records minted before this layout keep their committed logs under
`sim/*/corners/`; history is untouched.
