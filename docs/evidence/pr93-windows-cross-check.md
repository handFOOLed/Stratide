# PR #93 — Windows cross-check evidence (cloud agent)

Recorded on branch `cursor/settings-status-wsl-health-474a` with **Rust 1.99.1** (`rustup run stable`).

## PASS — whole-service type-check (GNU Windows target)

```bash
rustup run stable cargo check -p stratided --all-targets --locked --target x86_64-pc-windows-gnu
# Finished `dev` profile — includes lib, tests, bins (stratided/main.rs per-request threads)
```

Also:

```bash
rustup run stable cargo check -p stratide-runtime --all-targets --locked --target x86_64-pc-windows-msvc
# Finished
```

## FAIL — MSVC target (production toolchain on Owner machine)

```bash
rustup run stable cargo check -p stratided --all-targets --locked --target x86_64-pc-windows-msvc
# ring build: fatal error: 'assert.h' file not found (no Windows SDK on Linux VM)
```

Owner/installer uses MSVC via `scripts/with-msvc.ps1` / `scripts/build-windows-installer.ps1`; re-run the same `cargo check`/`cargo test` there after merge.

## FAIL — linked test binaries on GNU cross (VM linker)

```bash
rustup run stable cargo test -p stratided --lib runtime_status_cache --locked --target x86_64-pc-windows-gnu
# x86_64-w64-mingw32-ld: cannot find -lAdvapi32 (winapi crate mixed-case link name)
```

Unit test **sources** for `runtime_status_cache` are type-checked by the GNU `cargo check --all-targets` above; execution blocked by linker.

## PASS — portable frontend tests

```bash
cd apps/dashboard && node --test tests/status.test.js
# 9/9
```
