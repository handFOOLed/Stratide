"""Production headless entry: actual process clock, no test injection options."""
from eod_auto import main

if __name__ == "__main__":
    raise SystemExit(main())
