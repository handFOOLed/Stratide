Recorded CI run: see `.github/workflows/pr93-windows-settings-status.yml` (windows-latest, public repo).

## PASS — whole-service type-check (GNU, cloud VM fallback)

```bash
rustup run stable cargo check -p stratided --all-targets --locked --target x86_64-pc-windows-gnu
```

## MSVC — authoritative via GitHub Actions

Workflow **PR93 Windows settings status** on `windows-latest` runs:

- `cargo check -p stratided --all-targets --locked`
- `cargo test -p stratide-runtime --locked`
- `cargo test -p stratided runtime_status_cache --locked -- --test-threads=1`
- `cargo test -p stratided --test runtime_status_health --locked`
- `npm ci && npm run typecheck && npm run build && npm test` in `apps/dashboard`

Latest green MSVC run (PR #93): https://github.com/handFOOLed/Stratide/actions/runs/42160159527 @ `82e674b`.
