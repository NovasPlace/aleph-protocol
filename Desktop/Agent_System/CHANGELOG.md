# Changelog — Agent System

All notable changes to the Agent System will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2026-03-31

### Added
- **Documentation Overhaul**: Root README redesigned as a professional interface.
- **Directory Mapping**: Legacy README moved to `DIRECTORY_MAP.md`.
- **Standard Repo Files**: Added `LICENSE`, `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`, and `CODE_OF_CONDUCT.md`.
- **Organ Documentation**: Automated documentation pass for all 32 cognitive organs in `/organs`.
- **SEA Manifesto**: Formalized the Sovereign Engine Architecture version 1.0.
- **Onboarding Pipeline**: `onboarding.py` unified as the primary entry point for context assembly.

### Fixed
- **Root Pathing**: Audited root-level accessibility for sub-modules.
- **Context Fragmentation**: Unified internal naming conventions for the "Sovereign Engine" vs "Agent System".

---

## [0.0.1] — 2026-03-21

### Added
- Initial directory structure (Organs, Daemons, Tools).
- Core `Sovereign_Engine_Core` baseline.
- `aleph-edge-node` Cloudflare worker.
- Primary cognitive organs: `Cortex`, `Goal-Stack`, `Adaptive-Cognition`.
