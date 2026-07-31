# Privacy audit — v0.4.4 GitHub package

Checked before publication:

- No user `config.yaml`, `state.json`, local `gtfs.zip`, activity log, or exported diagnostic.
- No runtime authentication token, cookie, credential, or persisted device identifier.
- No Windows user-profile path or machine-specific installation folder.
- No virtual environment, build directory, or Python cache files.
- `config.example.yaml` contains example/default values only.
- Names and coordinates used in tests/documentation refer to public transit examples and are not imported from a user's runtime files.

Intended public personal attribution:

- Author/copyright: Miftahul Ardli.
