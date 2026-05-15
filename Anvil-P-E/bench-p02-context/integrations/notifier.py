"""Notification integrations for GitHub PRs and Slack alerts."""

import base64
import os

import httpx


def raise_github_pr(service: str, incident_id: str, context: dict) -> None:
    """Create a GitHub PR with an RCA markdown file for the incident.

    Silently no-ops if GITHUB_TOKEN or GITHUB_REPO env vars are not set.

    Args:
        service: The canonical service name.
        incident_id: The incident identifier.
        context: The reconstructed context dict from reconstruct_context().
    """
    token = os.getenv("GITHUB_TOKEN", "")
    repo = os.getenv("GITHUB_REPO", "")

    if not token or not repo:
        print("GitHub notifier: env vars not set, skipping")
        return

    try:
        branch = f"engram-fix/{service}/{incident_id[:8]}"
        filepath = f"rca/{service}-{incident_id[:8]}.md"

        causal_chain = context.get("causal_chain", [])
        similar = context.get("similar_past_incidents", [])
        remediations = context.get("suggested_remediations", [])
        action = remediations[0].get("action", "investigate") if remediations else "investigate"
        confidence = context.get("confidence", 0.0)
        explain = context.get("explain", "")

        content = (
            f"# RCA: {incident_id}\n\n"
            f"**Service:** {service}\n\n"
            f"**Causal Chain:** {len(causal_chain)} edges\n\n"
            f"**Similar Past Incidents:** {len(similar)}\n\n"
            f"**Suggested Action:** {action}\n\n"
            f"**Confidence:** {confidence:.2f}\n\n"
            f"## Explanation\n\n"
            f"{explain}\n"
        )

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        api = f"https://api.github.com/repos/{repo}"

        # Get base SHA from main branch
        resp = httpx.get(f"{api}/git/refs/heads/main", headers=headers)
        resp.raise_for_status()
        base_sha = resp.json()["object"]["sha"]

        # Create branch
        httpx.post(
            f"{api}/git/refs",
            headers=headers,
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        ).raise_for_status()

        # Create file in the new branch
        encoded = base64.b64encode(content.encode()).decode()
        httpx.put(
            f"{api}/contents/{filepath}",
            headers=headers,
            json={
                "message": f"RCA: {incident_id} on {service}",
                "content": encoded,
                "branch": branch,
            },
        ).raise_for_status()

        # Open pull request
        httpx.post(
            f"{api}/pulls",
            headers=headers,
            json={
                "title": f"[Engram] RCA: {incident_id} on {service}",
                "head": branch,
                "base": "main",
                "body": content,
            },
        ).raise_for_status()

    except Exception as e:
        print(f"GitHub notifier error: {e}")
        return


def notify_slack(incident_id: str, service: str, action: str) -> None:
    """Send a Slack notification about an incident resolution.

    Silently no-ops if SLACK_WEBHOOK_URL env var is not set.

    Args:
        incident_id: The incident identifier.
        service: The canonical service name.
        action: The remediation action taken.
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        return

    try:
        httpx.post(
            webhook_url,
            json={"text": f"Engram resolved {incident_id} on {service}. Action: {action}"},
        )
    except Exception:
        pass
