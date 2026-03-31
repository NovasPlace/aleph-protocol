# Contributing to the Agent System

First, thank you for considering contributing to the advancement of autonomous digital organisms. This project is a collaboration between human staff-level engineers and autonomous fabrication agents.

## 🗝️ The Golden Rule: The Execution Proof Law

**Never submit code that you haven't executed.** 

Whether you are a human or an agent, any pull request that claims functionality without providing raw execution output (logs, terminal captures, or screenshots) will be rejected immediately. We value evidence over hypotheses.

## 🧬 Architectural Alignment

All contributions must adhere to the **Sovereign Engine Architecture (SEA)**. Before proposing changes, read the [SEA Manifesto](SEA_Manifesto.md).

### Design Principles:
- **Composition over Inheritance**: Keep class hierarchies shallow.
- **Zero-Trust**: Use the mandatory 7-stage pre-ship pipeline.
- **Observability**: Every new handler must emit to the Trace Ledger.
- **No Frameworks**: Avoid adding heavy dependencies unless absolutely necessary. Stick to the core stack (Python/FastAPI, Electron/JS, PostgreSQL).

## 🤖 Agentic Contributions

If you are an AI agent contributing to this repository:
1. **Identify Yourself**: Start your PR with your agent name and version.
2. **Tag your Basis**: Explicitly state if your changes are based on fresh file reads `[source-read]` or memory `[from-memory]`.
3. **Run the Gauntlet**: Ensure all verification tests pass on your specific hardware environment before submission.

## 🛠️ Development Workflow

1.  **Onboard**: Run `python3 onboarding.py` to sync local context.
2.  **Plan**: Draft your approach in an `implementation_plan.md` artifact.
3.  **Execute**: Build surgically. Avoid refactoring adjacent code.
4.  **Verify**: Show terminal receipts in your PR description.
5.  **Harden**: Ensure input sanitization and OOM guards are in place.

## 🛡️ Security Protocol

Do not submit credentials, API keys, or hardcoded secrets. Use the `.env.example` template for configuration.

---

*Authored by Frost & Antigravity*
