# Organs: Blueprint Forge

**Component Type**: Sovereign Engine Cognitive Organ
**Status**: Active / Production

## Role
BlueprintForge — Blueprint Generation for the Sovereign Organism.

Generates structured blueprints from natural language intents.
Blueprints describe plans, architectures, or designs as structured dicts.

Usage:
    from blueprint_forge.forge import forge
    from blueprint_forge.models import ForgeRequest
    req = ForgeRequest(intent="build a REST API for task management", domain="software")
    blueprint = await forge(req)

---
*Part of the Sovereign Engine Architecture (SEA)*
