# ◈ Code Cortex

**Autonomous codebase awareness and self-repair engine.**

A [Manifesto Engine](https://manifesto-engine.com) tool.

---

Code Cortex watches your codebase, detects problems before they surface, and repairs what it can autonomously. It's not a linter — it's a living awareness layer that understands the *relationships* between your files, your imports, your types, and your dependencies.

## What It Detects

| Analyzer | What It Finds | Severity |
|----------|--------------|----------|
| **Dead Code** | Unused exports, unreferenced functions | Low |
| **Stale Imports** | Imports pointing to deleted/moved files or missing symbols | High |
| **Circular Deps** | Dependency cycles between modules | Medium–High |
| **Orphan Files** | Files never imported by anything | Low |
| *Complexity Spike* | Sudden complexity increases *(v0.2)* | Medium |
| *Deprecated Usage* | Usage of deprecated APIs *(v0.2)* | Medium |

## Quick Start

```bash
# Install
npm install -g @manifesto-engine/code-cortex

# Initialize config
cortex init

# Scan your codebase
cortex scan

# Output as JSON for CI pipelines
cortex scan -o json

# Only show critical/high issues
cortex scan --min-severity high

# Export a markdown report
cortex scan -o markdown > cortex-report.md
```

## How It Works

1. **Scan** — Reads every file matching your config patterns, builds an AST-level understanding of exports, imports, and dependency relationships.

2. **Analyze** — Runs each enabled analyzer in parallel. Every analyzer produces typed `CortexIssue` objects with severity, confidence scores, and repair strategies.

3. **Report** — Outputs results in terminal (default), JSON, Markdown, or MCP format. Exit codes reflect severity (2 = critical, 1 = high, 0 = clean).

4. **Provenance** — Every scan produces a SHA-256 provenance chain. Each scan hashes the codebase state and links to the previous scan, creating an auditable history of your codebase's health over time.

## Configuration

Create a `cortex.config.json` in your project root (or run `cortex init`):

```json
{
  "root": ".",
  "include": ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"],
  "exclude": ["**/node_modules/**", "**/dist/**"],
  "analyzers": [
    { "name": "dead-code", "enabled": true },
    { "name": "stale-imports", "enabled": true },
    { "name": "circular-deps", "enabled": true },
    { "name": "orphan-files", "enabled": true }
  ],
  "minConfidence": 60,
  "minSeverity": "low",
  "autoRepair": false,
  "maxIssues": 500,
  "output": "terminal",
  "provenancePath": ".cortex/provenance.json"
}
```

## Programmatic API

```typescript
import {
  CortexEngine,
  scanFiles,
  createAllAnalyzers,
  mergeConfig,
  reportToTerminal,
} from "@manifesto-engine/code-cortex";

const config = mergeConfig({ root: "./src" });
const files = await scanFiles(config);

const engine = new CortexEngine(config);
for (const analyzer of createAllAnalyzers()) {
  engine.registerAnalyzer(analyzer);
}

const result = await engine.scan(files);
console.log(reportToTerminal(result));
```

## CI Integration

Code Cortex is designed to run in CI pipelines. It exits with:
- **0** — No high/critical issues
- **1** — High severity issues found
- **2** — Critical severity issues found

```yaml
# CI Automation
- name: Code Cortex Scan
  run: npx @manifesto-engine/code-cortex scan -o json --min-severity high
```

## Roadmap

- [x] Dead code detection
- [x] Stale import detection
- [x] Circular dependency detection
- [x] Orphan file detection
- [x] SHA-256 provenance chains
- [ ] Watch mode (continuous scanning)
- [ ] Auto-repair engine
- [ ] Complexity spike detection
- [ ] Deprecated API usage detection
- [ ] MCP server mode (for agent integration)
- [ ] CI Action (first-party)
- [ ] VS Code extension

## Philosophy

Code Cortex is built on the Manifesto Engine principle: **infrastructure should be autonomous, sovereign, and self-maintaining.** Your codebase is a living system. It should have its own immune system.

---

Built by [Frost](https://manifesto-engine.com) 
