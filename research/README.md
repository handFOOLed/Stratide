# Research subsystem (future)

Cloud-only LLM APIs; no local model runtime. Untrusted generated code executes only in isolated, budgeted workers (prefer remote when local footprint matters). A separate independent evaluator validates results; research agents cannot approve their own artifacts or edit production risk rules. Do not start implementing until `grill-with-docs` agrees on the artifact boundary.
