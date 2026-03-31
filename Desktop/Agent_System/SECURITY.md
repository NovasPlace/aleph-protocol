# Security Policy — Agent System

> "Safety == Trust."

The Agent System is a persistent, autonomous software organism. Its core safety logic is based on the **Execution Proof Law** and raw-input validation.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| v0.1.x | ✅ Yes            |
| < v0.1 | ❌ No              |

## Verification Protocol

Every change submitted to the repository must pass our **7-Stage Pre-Ship Pipeline**:
1. **Functional**: Happy path verification.
2. **User-Friendly**: Operator-readability.
3. **Bug Sweep**: Adversarial input testing.
4. **Verification**: Raw execution logs.
5. **Hardening**: Sanitization and isolation.
6. **Review**: Human operator approval.
7. **Ship**: Final deployment.

## Reporting a Vulnerability

If you've discovered a vulnerability in the Agent System, please report it via the following structured Mayday payload to the project administrator (**Frost**):

```json
{
    "mayday": true,
    "security_vulnerability": "<description>",
    "severity": "<low/medium/high/critical>",
    "reproduction_steps": "<steps>",
    "impact": "<data leak, RCE, sandbox escape, etc.>"
}
```

Please do not open a public issue for security-sensitive bugs. We aim to respond within 24 hours.

## Disclosure Policy

We follow a 90-day disclosure deadline. After a fix is shipped, we will publish a post-mortem on the Trace Ledger.

## Non-Disclosure of Secrets

**ABSOLUTELY NO SECRETS IN SOURCE CODE.**
- Use `.env` files for local configuration.
- Check `.gitignore` before every commit.
- Use `system-debugger` tools to audit environment leaks.

---

*Verified by Antigravity*
