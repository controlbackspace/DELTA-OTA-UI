# Gateway Project — Domain & Dev Conventions

## Architecture
- Python AsyncIO Edge Gateway daemon (headless)
- Domain models in `secureota/gateway/domain/` — pure dataclasses + enums, zero external deps
- Lifecycle entity: `StagedPatch` with validated state machine transitions
- No framework dependencies in the domain layer (no FastAPI, no SQLAlchemy, no web3.py in domain/)

## Conventions
- Domain aggregate files prefixed with `_` (e.g. `_models.py`, `_enums.py`) to signal internal implementation detail
- All domain validation in `__post_init__` (frozen dataclasses) or `transition()` methods
- Wire format using `struct.pack`/`unpack` for deterministic binary serialization
- Tests in project root as standalone Python scripts (no test framework required)

## Running Tests
```bash
python quick_test.py
```

## State Machine Reminder
`StagedPatch` transitions are strict — see `_models.py:transition()` for the full DAG. Illegal transitions raise `ValueError`.
