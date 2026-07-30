# Thesis Project — Master Instructions

## Project Structure
```
Projects/thesis/
├── gateway/          # Python AsyncIO Edge Gateway (Bounded Context 3)
│   ├── secureota/gateway/domain/   # Core domain models
│   ├── SESSION_STATE.md            # Session checkpoint & glossary
│   ├── AGENTS.md                   # Gateway-specific instructions
│   └── quick_test.py              # Smoke test
├── ui/
│   └── secureota-ui/ # React/TypeScript Developer GUI (Bounded Context 1)
│       ├── src/
│       ├── AGENTS.md               # UI-specific instructions
│       └── ...
├── contracts/        # (future) Solidity ManifestRegistry (Bounded Context 2)
├── firmware/         # (future) ESP32 C/C++ target (Bounded Context 4)
└── AGENTS.md         # <-- THIS FILE
```

## Working With This Repo

### Always start by reading SESSION_STATE.md
Before any work, read `gateway/SESSION_STATE.md` to understand current domain state, decisions, and what's pending. Update it when a session ends.

### Domain-Driven Design Protocol
- Extract Ubiquitous Language before writing implementation code
- Define Bounded Contexts, Aggregates, Value Objects, Domain Events
- Require explicit justification for state transitions and domain invariants
- Don't jump to framework setup, schemas, or API routes until domain model is locked

### Each session
1. Read SESSION_STATE.md
2. Read the relevant AGENTS.md (gateway/ or ui/)
3. Pick up where we left off under "Pending"
4. Mark progress and decisions in SESSION_STATE.md before signing off
