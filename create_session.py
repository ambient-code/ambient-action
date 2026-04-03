#!/usr/bin/env python3
"""
Create an Ambient Code Platform session or send a message to an existing one.

Supports three modes:
- Create + fire-and-forget: create session and exit immediately
- Create + wait: create session then poll until terminal phase
- Send message: send a message to an existing session via AG-UI
"""

import argparse
import json
import logging
import sys
import time
import uuid

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

TERMINAL_PHASES = {"Completed", "Error", "Timeout", "Stopped", "Failed"}


def get_session_phase(
    api_url: str,
    api_token: str,
    project: str,
    session_name: str,
    verify_ssl: bool = True,
) -> str | None:
    """Get the current phase of a session. Returns None if session not found."""
    url = f"{api_url.rstrip('/')}/projects/{project}/agentic-sessions/{session_name}"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=15,
            verify=verify_ssl,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("status", {}).get("phase", "Unknown")
    except requests.RequestException as e:
        logger.error(f"Failed to get session {session_name}: {e}")
        return None


def start_session(
    api_url: str,
    api_token: str,
    project: str,
    session_name: str,
    verify_ssl: bool = True,
) -> bool:
    """Start/restart a stopped session."""
    url = f"{api_url.rstrip('/')}/projects/{project}/agentic-sessions/{session_name}/start"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=30,
            verify=verify_ssl,
        )
        resp.raise_for_status()
        logger.info(f"Session {session_name} start requested")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to start session {session_name}: {e}")
        return False


def ensure_session_running(
    api_url: str,
    api_token: str,
    project: str,
    session_name: str,
    verify_ssl: bool = True,
    max_wait: int = 60,
) -> bool:
    """Ensure session is running. Starts it if stopped, waits for Running phase."""
    phase = get_session_phase(api_url, api_token, project, session_name, verify_ssl)

    if phase is None:
        logger.error(f"Session {session_name} not found")
        return False

    if phase == "Running":
        return True

    if phase in TERMINAL_PHASES:
        logger.info(f"Session {session_name} is {phase}, starting...")
        if not start_session(api_url, api_token, project, session_name, verify_ssl):
            return False

    # Wait for session to reach Running (handles both restart and pending/starting phases)
    deadline = time.time() + max_wait
    while time.time() < deadline:
        phase = get_session_phase(api_url, api_token, project, session_name, verify_ssl)
        if phase == "Running":
            logger.info(f"Session {session_name} is now Running")
            return True
        if phase is None:
            logger.error(f"Session {session_name} disappeared")
            return False
        logger.info(f"Waiting for session {session_name} to reach Running (phase: {phase})")
        time.sleep(3)

    logger.error(f"Timed out waiting for session {session_name} to reach Running")
    return False


def send_message(
    api_url: str,
    api_token: str,
    project: str,
    session_name: str,
    message: str,
    verify_ssl: bool = True,
    startup_timeout: int = 120,
) -> bool:
    """Send a message to an existing session. Starts the session first if stopped."""
    if not ensure_session_running(api_url, api_token, project, session_name, verify_ssl, max_wait=startup_timeout):
        return False

    url = f"{api_url.rstrip('/')}/projects/{project}/agentic-sessions/{session_name}/agui/run"

    body = {
        "threadId": session_name,
        "runId": str(uuid.uuid4()),
        "messages": [
            {
                "id": str(uuid.uuid4()),
                "role": "user",
                "content": message,
            }
        ],
    }

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
        logger.info(f"Message sent to session {session_name}")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send message to session {session_name}: {e}")
        return False


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
    timeout: int = 0,
    stop_on_run_finished: bool = False,
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
        body["inactivityTimeout"] = timeout
    if stop_on_run_finished:
        body["stopOnRunFinished"] = True
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


AGENT_DONE_STATUSES = {"idle", "waiting_input"}


def poll_session(
    api_url: str,
    api_token: str,
    project: str,
    session_name: str,
    poll_interval: int = 15,
    timeout_minutes: int = 30,
    verify_ssl: bool = True,
) -> dict:
    """Poll session until the agent is done or session reaches a terminal phase.

    Exits when:
    - Session phase is terminal (Completed, Error, Timeout, Stopped, Failed)
    - Agent status is idle or waiting_input (agent finished its run, session still alive)
    """
    url = f"{api_url.rstrip('/')}/projects/{project}/agentic-sessions/{session_name}"
    headers = {"Authorization": f"Bearer {api_token}"}
    deadline = time.time() + (timeout_minutes * 60) + 120

    logger.info(
        f"Polling session {session_name} every {poll_interval}s "
        f"(timeout: {timeout_minutes}m + 2m buffer)"
    )

    seen_working = False
    while time.time() < deadline:
        try:
            resp = requests.get(
                url, headers=headers, timeout=15, verify=verify_ssl
            )
            resp.raise_for_status()
            data = resp.json()

            status = data.get("status", {})
            phase = status.get("phase", "Unknown")
            agent_status = status.get("agentStatus", "")

            logger.info(f"Session {session_name}: phase={phase}, agentStatus={agent_status}")

            if phase in TERMINAL_PHASES:
                return {
                    "phase": phase,
                    "agentStatus": agent_status,
                    "result": status.get("result", ""),
                    "completionTime": status.get("completionTime", ""),
                }

            # Track if the agent has been active at least once
            if agent_status and agent_status not in AGENT_DONE_STATUSES:
                seen_working = True

            # Only exit on idle/waiting_input after the agent has been working
            if seen_working and agent_status in AGENT_DONE_STATUSES:
                logger.info(f"Session {session_name}: agent is {agent_status}, done waiting")
                return {
                    "phase": phase,
                    "agentStatus": agent_status,
                    "result": status.get("result", ""),
                    "completionTime": "",
                }

        except requests.RequestException as e:
            logger.warning(f"Poll request failed (will retry): {e}")

        time.sleep(poll_interval)

    logger.error("Polling timed out waiting for session completion")
    return {"phase": "PollTimeout", "agentStatus": "", "result": "", "completionTime": ""}


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
        description="Create an Ambient Code Platform session or send a message to an existing one."
    )
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--api-token", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--prompt", default="")
    parser.add_argument("--prompt-file", default="", help="Read prompt from file (preferred over --prompt for multi-line content)")
    parser.add_argument("--session-name", default="", help="Existing session to send a message to (skips creation)")
    parser.add_argument("--display-name", default="")
    parser.add_argument("--repos", default="")
    parser.add_argument("--workflow", default="")
    parser.add_argument("--labels", default="")
    parser.add_argument("--env-vars", default="")
    parser.add_argument("--timeout", type=int, default=0)
    parser.add_argument("--stop-on-run-finished", action="store_true")
    parser.add_argument("--model", default="")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--no-verify-ssl", action="store_true")
    parser.add_argument("--poll-timeout", type=int, default=60, help="Max minutes to poll before giving up (only with --wait)")
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

    # Mode: send message to existing session
    if args.session_name:
        success = send_message(
            api_url=args.api_url,
            api_token=args.api_token,
            project=args.project,
            session_name=args.session_name,
            message=prompt,
            verify_ssl=verify_ssl,
            startup_timeout=args.poll_timeout * 60,
        )

        output = {
            "session_name": args.session_name,
            "session_uid": "",
            "session_phase": "MessageSent" if success else "MessageFailed",
            "session_result": "",
        }

        if not success:
            write_output(args.output_file, output)
            sys.exit(1)

        if args.wait:
            poll_result = poll_session(
                api_url=args.api_url,
                api_token=args.api_token,
                project=args.project,
                session_name=args.session_name,
                poll_interval=args.poll_interval,
                timeout_minutes=args.poll_timeout,
                verify_ssl=verify_ssl,
            )
            output["session_phase"] = poll_result.get("phase", "")
            output["session_result"] = poll_result.get("result", "")

        write_output(args.output_file, output)
        return

    # Mode: create new session
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
        stop_on_run_finished=args.stop_on_run_finished,
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
            timeout_minutes=args.poll_timeout,
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
