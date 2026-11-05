# Stratide Third-Party Notices

Stratide is a Paper-only local research and simulation product. This installer
does not include a live broker adapter, exchange credentials, DeepSeek API keys,
Tushare tokens or TimesFM model weights.

Bundled runtime components:

- **CPython 3.12.10 (embeddable, AMD64)** — Python Software Foundation License
  Version 2. Source: https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip
  SHA256: 4ACBED6DD1C744B0376E3B1CF57CE906F9DC9E95E68824584C8099A63025A3C3
- **tzdata 2026.6** (IANA timezone database for Python zoneinfo) — Apache License 2.0.
  SHA256: 0A10EEC6E13EF16B627FABED9A5F2BA61A62B1C67F327305F4E7E412A70B4AEC
- **Rust crates** listed in Cargo.lock retain their upstream licenses; the binary
  set is built from the pinned lock file.
- **Inno Setup 6.7.4** is used only to build the installer; it is not bundled
  as an application runtime.

TimesFM 2.5 and its weights are not bundled. The product reuses an existing
Owner-managed WSL2/ext4 environment when the Owner chooses to configure one;
the model license and provisioning remain the Owner's responsibility.

This file is informational and does not replace the license of any component.
