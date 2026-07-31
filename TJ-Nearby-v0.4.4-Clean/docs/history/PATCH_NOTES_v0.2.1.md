# TJ Nearby v0.2.1

## Fixed

- Fixed macOS `.app` build failure with py2app 0.28.9+ (`install_requires is no longer supported`).
- The app bundle is now built from an isolated temporary directory without project dependency metadata.
- Replaced editable package installation during app bundling with a normal installation, as required by current py2app releases.
- Added an executable-presence check before signing and installation.
- Updated deprecated license metadata syntax.

All v0.2.0 location, stop grouping, ETA, and automatic-login behavior is retained.
