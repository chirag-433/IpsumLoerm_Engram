"""LLM-powered explanation synthesis for incident context."""

import os


def synthesize_explanation(signal: dict, causal_chain: list,
                           similar_incidents: list, remediations: list) -> str:
    """Generate a natural-language incident summary using an LLM.

    Falls back to a template if no API key is set or the LLM call fails.
    Always returns a string, never raises.

    Args:
        signal: The incident signal dict.
        causal_chain: List of causal edge dicts.
        similar_incidents: List of similar past incident dicts.
        remediations: List of suggested remediation dicts.

    Returns:
        A concise operational summary string.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _template_explain(signal, causal_chain, similar_incidents, remediations)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            f"You are an SRE analyzing a production incident.\n"
            f"Incident: {signal.get('incident_id')} on {signal.get('service')} at {signal.get('ts')}\n"
            f"Trigger: {signal.get('trigger')}\n"
            f"Causal chain edges: {len(causal_chain)}\n"
            f"Similar past incidents: {len(similar_incidents)}\n"
            f"Top remediation: {remediations[0].get('action') if remediations else 'none'}\n"
            f"Write a 2-sentence operational summary. Be specific. No filler words."
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception:
        return _template_explain(signal, causal_chain, similar_incidents, remediations)


def _template_explain(signal: dict, causal_chain: list,
                      similar_incidents: list, remediations: list) -> str:
    """Build a deterministic template-based explanation as fallback."""
    svc = signal.get("service", "unknown")
    ts = signal.get("ts", "")
    action = remediations[0].get("action") if remediations else "investigate"
    return (
        f"Incident on {svc} at {ts}. "
        f"Causal chain: {len(causal_chain)} edges. "
        f"Similar past: {len(similar_incidents)}. "
        f"Suggested: {action}."
    )
