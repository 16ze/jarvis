"""
Module de dispatch vers les sous-agents asyncio.
Expose handle(tool_name, args, research_agent, task_agent, anticipation_agent, monitoring_agent).

Agents couverts :
- ResearchAgent  → run_research
- TaskAgent      → run_task
- AnticipationAgent → anticipate
- MonitoringAgent   → start_monitoring, stop_monitoring
"""

from typing import Any


async def handle(
    tool_name: str,
    args: dict[str, Any],
    research_agent: Any,
    task_agent: Any,
    anticipation_agent: Any,
    monitoring_agent: Any,
) -> str:
    """
    Dispatche vers le sous-agent approprié en fonction de tool_name.

    Outils supportés :
    - run_research(query)         → ResearchAgent.run(query)
    - run_task(objective)         → TaskAgent.run(objective)
    - anticipate(context)         → AnticipationAgent.run(context)
    - start_monitoring(watch_config) → MonitoringAgent.run(watch_config)
    - stop_monitoring()           → MonitoringAgent.stop()
    """
    try:
        if tool_name == "run_research":
            query = args.get("query", "")
            if not query:
                return "Erreur run_research : paramètre 'query' manquant."
            return await research_agent.run(query)

        elif tool_name == "run_task":
            objective = args.get("objective", "")
            if not objective:
                return "Erreur run_task : paramètre 'objective' manquant."
            return await task_agent.run(objective)

        elif tool_name == "anticipate":
            context = args.get("context", "")
            return await anticipation_agent.run(context)

        elif tool_name == "start_monitoring":
            watch_config = args.get("watch_config", "")
            return await monitoring_agent.run(watch_config)

        elif tool_name == "stop_monitoring":
            return await monitoring_agent.stop()

        return f"Outil agents inconnu : {tool_name}"

    except Exception as e:
        return f"Erreur {tool_name} : {e}"
