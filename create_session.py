#!/usr/bin/env python3
"""
Create an Ambient Code Platform session via the backend API.

Supports two modes:
- Fire-and-forget: create and exit immediately
- Wait-for-completion: create then poll until terminal phase
"""

import argparse
import json
import logging
import sys
import time

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

TERMINAL_PHASES = {"Completed", "Error", "Timeout", "Stopped", "Failed"}


def create_session(
    api_url: str,
    api_token: str,
    project: str,
    prompt: str,
    display_name: str = "",
    repos: list | None = None,
    workflow: dict | None = None,
    labels: dict | None = None,
    env_vars: dict | None = None,
    timeout: int = 30,
    model: str = "",
    verify_ssl: bool = True,
) -> dict | None:
    """POST to create an Ambient session. Returns the API response dict."""
    url = f"{api_url.rstrip('/')}/projects/{project}/agentic-sessions"

    body: dict = {"initialPrompt": prompt}

    if display_name:
        body["displayName"] = display_name
    if repos:
        body["repos"] = repos
    if workflow:
        body["activeWorkflow"] = workflow
    if labels:
        body["labels"] = labels
    if env_vars:
        body["environmentVariables"] = env_vars
    if timeout:
        body["timeout"] = timeout * 60
    if model:
        body["llmSettings"] = {"model": model}

    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
            verify=verify_ssl,
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info(
            f"Session created: name={result.get('name', '?')}, "
            f"uid={result.get('uid', '?')}"
        )
        return result
    except requests.RequestException as e:
        logger.error(f"Failed to create session: {e}")
        return None


def poll_session(
    api_url: str,
    api_token: str,
    project: str,
    session_name: str,
    poll_interval: int = 15,
    timeout_minutes: int = 30,
    verify_ssl: bool = True,
) -> dict:
    """Poll session status until a terminal phase is reached."""
    url = f"{api_url.rstrip('/')}/projects/{project}/agentic-sessions/{session_name}"
    headers = {"Authorization": f"Bearer {api_token}"}
    deadline = time.time() + (timeout_minutes * 60) + 120

    logger.info(
        f"Polling session {session_name} every {poll_interval}s "
        f"(timeout: {timeout_minutes}m + 2m buffer)"
    )

    while time.time() < deadline:
        try:
            resp = requests.get(
                url, headers=headers, timeout=15, verify=verify_ssl
            )
            resp.raise_for_status()
            data = resp.json()

            status = data.get("status", {})
            phase = status.get("phase", "Unknown")

            logger.info(f"Session {session_name}: phase={phase}")

            if phase in TERMINAL_PHASES:
                return {
                    "phase": phase,
                    "result": status.get("result", ""),
                    "completionTime": status.get("completionTime", ""),
                }

        except requests.RequestException as e:
            logger.warning(f"Poll request failed (will retry): {e}")

        time.sleep(poll_interval)

    logger.error("Polling timed out waiting for session completion")
    return {"phase": "PollTimeout", "result": "", "completionTime": ""}


def write_output(output_file: str, data: dict) -> None:
    """Write JSON output to a file for the entrypoint to parse."""
    if not output_file:
        return
    try:
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Output written to {output_file}")
    except Exception as e:
        logger.warning(f"Failed to write output file: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Create an Ambient Code Platform session."
    )
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--api-token", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--prompt", default="")
    parser.add_argument("--prompt-file", default="", help="Read prompt from file (preferred over --prompt for multi-line content)")
    parser.add_argument("--display-name", default="")
    parser.add_argument("--repos", default="")
    parser.add_argument("--workflow", default="")
    parser.add_argument("--labels", default="")
    parser.add_argument("--env-vars", default="")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--model", default="")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--no-verify-ssl", action="store_true")
    parser.add_argument("--output-file", default="")

    args = parser.parse_args()

    # Resolve prompt: --prompt-file takes precedence over --prompt
    prompt = args.prompt
    if args.prompt_file:
        try:
            with open(args.prompt_file) as f:
                prompt = f.read()
        except OSError as e:
            logger.error(f"Failed to read prompt file: {e}")
            sys.exit(1)
    if not prompt:
        parser.error("either --prompt or --prompt-file is required")

    verify_ssl = not args.no_verify_ssl

    if not verify_ssl:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    repos = json.loads(args.repos) if args.repos else None
    workflow = json.loads(args.workflow) if args.workflow else None
    labels = json.loads(args.labels) if args.labels else None
    env_vars = json.loads(args.env_vars) if args.env_vars else None

    result = create_session(
        api_url=args.api_url,
        api_token=args.api_token,
        project=args.project,
        prompt=prompt,
        display_name=args.display_name,
        repos=repos,
        workflow=workflow,
        labels=labels,
        env_vars=env_vars,
        timeout=args.timeout,
        model=args.model,
        verify_ssl=verify_ssl,
    )

    if not result:
        logger.error("Session creation failed")
        write_output(args.output_file, {
            "session_name": "",
            "session_uid": "",
            "session_phase": "CreateFailed",
            "session_result": "",
        })
        sys.exit(1)

    session_name = result.get("name", "")
    session_uid = result.get("uid", "")

    output = {
        "session_name": session_name,
        "session_uid": session_uid,
        "session_phase": "",
        "session_result": "",
    }

    if args.wait and session_name:
        poll_result = poll_session(
            api_url=args.api_url,
            api_token=args.api_token,
            project=args.project,
            session_name=session_name,
            poll_interval=args.poll_interval,
            timeout_minutes=args.timeout,
            verify_ssl=verify_ssl,
        )
        output["session_phase"] = poll_result.get("phase", "")
        output["session_result"] = poll_result.get("result", "")

        if poll_result["phase"] in ("Error", "Failed", "PollTimeout"):
            logger.error(f"Session ended with phase: {poll_result['phase']}")
    else:
        logger.info("Fire-and-forget mode — not waiting for completion")

    write_output(args.output_file, output)


if __name__ == "__main__":
    main()
