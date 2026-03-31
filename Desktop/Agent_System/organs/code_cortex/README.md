# Organs: Code Cortex

**Component Type**: Sovereign Engine Cognitive Organ
**Status**: Active / Production

## Role
CodeCortex — Python in-process stub for the Sovereign Organism.

Wraps the TypeScript Code Cortex service (port 3200).
Provides in-process code analysis interface when service is unavailable.

Usage:
    from code_cortex import CodeCortex
    cc = CodeCortex()
    result = cc.analyze("/path/to/file.py")

---
*Part of the Sovereign Engine Architecture (SEA)*
