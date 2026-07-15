"""Specialist registry. Each specialist module defines SPECIALIST; this
package collects them into the SPECIALISTS dict the orchestrator fans out."""

from __future__ import annotations

from swarm.agents import comms, fact_checker, legal, social

SPECIALISTS = {
    module.SPECIALIST.name: module.SPECIALIST
    for module in (fact_checker, legal, comms, social)
}
