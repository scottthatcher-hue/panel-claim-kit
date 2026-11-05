#!/usr/bin/env python3
"""Panel Claim Kit: a registrar-mediated machine-claim prototype.

This tool records whether panel members want machine time, what kind of
access they can actually use, and how a human/registrar approves, queues,
claims, releases, and expires that time.

It deliberately does NOT control a computer, launch an agent, open a browser,
or grant credentials.  Approval in this tool is bookkeeping only.  A separate
operator still performs (or explicitly enables) any real machine session.

Stdlib only.  State is a local JSON document with atomic writes and an
append-only JSONL audit log beside it.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import fcntl  # POSIX advisory locks; harmless no-op elsewhere.
except Exception:  # pragma: no cover
    fcntl = None  # type: ignore

VERSION = "0.1.1"

ACCESS_LEVELS = [
    "none",
    "reservation_request",
    "registrar_launched",
    "prepared_task",
    "self_launch",
]

PREFERENCES = ["accept", "decline", "undecided"]
PRIORITIES = ["low", "normal", "high", "urgent"]
PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}

REQUEST_STATUSES = [
    "requested",
    "queued",
    "claimed",
    "released",
    "denied",
    "withdrawn",
    "declined",
    "no_access_requested",
    "capability_blocked",
    "expired",
]

DEFAULT_POLICY = {
    "registrar_required": True,
    "self_launch_enabled": False,
    "owner_approval_required_for_self_launch": True,
    "default_duration_minutes": 60,
    "max_duration_minutes": 240,
    "request_ttl_hours": 72,
    "queue_ttl_hours": 168,
    "stale_after_minutes": 120,
}


class ClaimError(Exception):
    """Raised for validation or workflow errors that should be shown cleanly."""


# ---------------------------------------------------------------------------
# Time and small helpers
# ---------------------------------------------------------------------------

def parse_time(value: Optional[str]) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.timezone.utc)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "seat"


def bool_value(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1"}:
            return True
        if lowered in {"false", "no", "n", "0", ""}:
            return False
    raise ClaimError(f"{field} must be a boolean")


def clean_public_title(value: Any) -> str:
    if not isinstance(value, str):
        raise ClaimError("public_title must be a string")
    title = " ".join(value.split())
    if not title:
        raise ClaimError("public_title is required")
    if len(title) > 90:
        raise ClaimError("public_title must be 90 characters or fewer")
    return title


# ---------------------------------------------------------------------------
# State storage
# ---------------------------------------------------------------------------

def audit_path_for(state_path: Path) -> Path:
    return state_path.with_suffix(state_path.suffix + ".audit.jsonl")


@contextlib.contextmanager
def state_lock(state_path: Path):
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def load_state(state_path: Path) -> Dict[str, Any]:
    if not state_path.exists():
        raise ClaimError(f"state file does not exist: {state_path} (run init first)")
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ClaimError(f"state file is not valid JSON: {exc}") from exc


def save_state(state_path: Path, state: Dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = iso(parse_time(state.get("_now_override")) if state.get("_now_override") else dt.datetime.now(dt.timezone.utc))
    state.pop("_now_override", None)
    fd, tmp_name = tempfile.mkstemp(prefix=state_path.name + ".", dir=str(state_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, state_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def append_audit(state_path: Path, event: Dict[str, Any]) -> None:
    path = audit_path_for(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def audit(state_path: Path, state: Dict[str, Any], action: str, actor: str, request_id: Optional[str], details: Dict[str, Any]) -> None:
    append_audit(
        state_path,
        {
            "at": iso(current_time(state)),
            "action": action,
            "actor": actor,
            "request_id": request_id,
            "details": details,
        },
    )


def current_time(state: Dict[str, Any]) -> dt.datetime:
    return parse_time(state.get("_now_override"))


# ---------------------------------------------------------------------------
# Validation and workflow
# ---------------------------------------------------------------------------

def get_machine(state: Dict[str, Any], machine_id: str) -> Dict[str, Any]:
    machines = state.get("machines", {})
    if machine_id not in machines:
        raise ClaimError(f"unknown machine: {machine_id}")
    return machines[machine_id]


def get_seat(state: Dict[str, Any], requester: str) -> Dict[str, Any]:
    seats = state.get("seats", {})
    if requester not in seats:
        raise ClaimError(f"unknown requester/seat: {requester}")
    return seats[requester]


def find_request(state: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    for request in state.get("requests", []):
        if request.get("id") == request_id:
            return request
    raise ClaimError(f"unknown request: {request_id}")


def normalize_request(state: Dict[str, Any], raw: Dict[str, Any], now: dt.datetime) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ClaimError("request must be a JSON object")

    requester = str(raw.get("requester", "")).strip()
    machine_id = str(raw.get("machine", "")).strip()
    if not requester:
        raise ClaimError("requester is required")
    if not machine_id:
        raise ClaimError("machine is required")
    get_seat(state, requester)
    get_machine(state, machine_id)

    preference = str(raw.get("preference", "accept")).strip().lower()
    if preference not in PREFERENCES:
        raise ClaimError(f"preference must be one of: {', '.join(PREFERENCES)}")

    requested_access = str(raw.get("requested_access", "none")).strip().lower()
    if requested_access not in ACCESS_LEVELS:
        raise ClaimError(f"requested_access must be one of: {', '.join(ACCESS_LEVELS)}")

    if preference == "decline":
        requested_access = "none"

    policy = state.get("policy", DEFAULT_POLICY)
    duration = raw.get("duration_minutes", policy.get("default_duration_minutes", 60))
    try:
        duration = int(duration)
    except Exception as exc:
        raise ClaimError("duration_minutes must be an integer") from exc
    if duration <= 0:
        raise ClaimError("duration_minutes must be positive")
    if duration > int(policy.get("max_duration_minutes", 240)):
        raise ClaimError(f"duration_minutes exceeds policy maximum ({policy['max_duration_minutes']})")

    proposed_priority = str(raw.get("proposed_priority", "normal")).strip().lower()
    if proposed_priority not in PRIORITIES:
        raise ClaimError(f"proposed_priority must be one of: {', '.join(PRIORITIES)}")

    caps_raw = raw.get("capabilities", {}) or {}
    if not isinstance(caps_raw, dict):
        raise ClaimError("capabilities must be an object")
    capabilities = {
        "can_request": bool_value(caps_raw.get("can_request", True), "capabilities.can_request"),
        "can_self_launch": bool_value(caps_raw.get("can_self_launch", False), "capabilities.can_self_launch"),
        "can_monitor": bool_value(caps_raw.get("can_monitor", False), "capabilities.can_monitor"),
        "can_release": bool_value(caps_raw.get("can_release", False), "capabilities.can_release"),
    }

    if requested_access != "none" and not capabilities["can_request"]:
        status = "capability_blocked"
    elif preference == "decline":
        status = "declined"
    elif requested_access == "none":
        status = "no_access_requested"
    elif requested_access == "self_launch" and not capabilities["can_self_launch"]:
        status = "capability_blocked"
    else:
        status = "requested"

    request_id = raw.get("id") or (
        f"req_{now.strftime('%Y%m%d%H%M%S')}_{slugify(requester)}_{secrets.token_hex(2)}"
    )

    return {
        "id": str(request_id),
        "requester": requester,
        "machine": machine_id,
        "preference": preference,
        "requested_access": requested_access,
        "public_title": clean_public_title(raw.get("public_title", "Panel machine work")),
        "private_details": str(raw.get("private_details", "")),
        "reason": str(raw.get("reason", "")),
        "duration_minutes": duration,
        "needed_by": str(raw.get("needed_by", "")),
        "proposed_priority": proposed_priority,
        "effective_priority": None,
        "capabilities": capabilities,
        "owner_approval_ref": str(raw.get("owner_approval_ref", "")),
        "status": status,
        "created_at": iso(now),
        "updated_at": iso(now),
        "approved_at": None,
        "approved_by": None,
        "claimed_at": None,
        "released_at": None,
        "last_heartbeat_at": None,
        "expires_at": None,
        "decision_note": "",
    }


def queue_for_machine(state: Dict[str, Any], machine_id: str) -> List[Dict[str, Any]]:
    queued = [
        r for r in state.get("requests", [])
        if r.get("machine") == machine_id and r.get("status") == "queued"
    ]
    return sorted(
        queued,
        key=lambda r: (
            PRIORITY_RANK.get(r.get("effective_priority") or "normal", 2),
            r.get("approved_at") or r.get("created_at") or "",
            r.get("created_at") or "",
        ),
    )


def promote_claim(state: Dict[str, Any], request: Dict[str, Any], actor: str, now: dt.datetime) -> None:
    machine = get_machine(state, request["machine"])
    if machine.get("active_claim"):
        raise ClaimError(f"machine {request['machine']} already has an active claim")
    request["status"] = "claimed"
    request["claimed_at"] = iso(now)
    request["last_heartbeat_at"] = iso(now)
    request["expires_at"] = iso(now + dt.timedelta(minutes=int(request["duration_minutes"])))
    request["updated_at"] = iso(now)
    machine["active_claim"] = request["id"]
    machine["updated_at"] = iso(now)


# ---------------------------------------------------------------------------
# Markdown intake parsing
# ---------------------------------------------------------------------------

TRUE_WORDS = {"yes", "true", "y", "1"}
FALSE_WORDS = {"no", "false", "n", "0", ""}

KEY_ALIASES = {
    "requester": "requester",
    "seat": "requester",
    "machine": "machine",
    "preference": "preference",
    "requested access": "requested_access",
    "access": "requested_access",
    "public title": "public_title",
    "title": "public_title",
    "private details": "private_details",
    "reason": "reason",
    "duration minutes": "duration_minutes",
    "duration": "duration_minutes",
    "needed by": "needed_by",
    "proposed priority": "proposed_priority",
    "priority": "proposed_priority",
    "owner approval ref": "owner_approval_ref",
    "can request": "can_request",
    "can self launch": "can_self_launch",
    "can self-launch": "can_self_launch",
    "can monitor": "can_monitor",
    "can release": "can_release",
}


def extract_panel_claim_block(text: str) -> str:
    match = re.search(r"```(?:panel-claim)?\s*\n(.*?)```", text, re.S | re.I)
    return match.group(1) if match else text


def parse_markdown_request(text: str) -> Dict[str, Any]:
    block = extract_panel_claim_block(text)
    values: Dict[str, Any] = {}
    capabilities: Dict[str, Any] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = " ".join(key.strip().lower().replace("_", " ").split())
        target = KEY_ALIASES.get(normalized_key)
        if not target:
            continue
        value = value.strip()
        if target in {"can_request", "can_self_launch", "can_monitor", "can_release"}:
            lowered = value.lower()
            if lowered in TRUE_WORDS:
                capabilities[target] = True
            elif lowered in FALSE_WORDS:
                capabilities[target] = False
            else:
                raise ClaimError(f"{key} must be yes or no")
        elif target == "duration_minutes":
            values[target] = int(value)
        else:
            values[target] = value
    if capabilities:
        values["capabilities"] = capabilities
    return values


# ---------------------------------------------------------------------------
# Board rendering
# ---------------------------------------------------------------------------

def render_board(state: Dict[str, Any], machine_id: str) -> str:
    machine = get_machine(state, machine_id)
    active_id = machine.get("active_claim")
    lines: List[str] = []
    label = machine.get("label", machine_id)
    lines.append(f"## {label}")
    lines.append("")
    if active_id:
        active = find_request(state, active_id)
        seat = state.get("seats", {}).get(active["requester"], {})
        display = seat.get("display_name", active["requester"])
        lines.append("- **Status:** CLAIMED")
        lines.append(f"- **Claimed by:** {display} (panel claim {active['id']})")
        if active.get("claimed_at"):
            lines.append(f"- **Since:** {active['claimed_at']}")
        lines.append(f"- **Current work:** {active['public_title']}")
    else:
        lines.append("- **Status:** FREE")
        lines.append("- **Claimed by:** —")
    lines.append("- **Queue:**")
    queue = queue_for_machine(state, machine_id)
    if not queue:
        lines.append("  1. —")
    else:
        for idx, request in enumerate(queue, start=1):
            seat = state.get("seats", {}).get(request["requester"], {})
            display = seat.get("display_name", request["requester"])
            tag = ""
            if idx == 1:
                tag = " — On deck"
            elif idx == 2:
                tag = " — In the hole"
            lines.append(
                f"  {idx}. {display} — {request['public_title']} "
                f"[{request['requested_access']}, {request.get('effective_priority') or 'normal'}]{tag}"
            )
    lines.append("")
    lines.append("_Rendered by Panel Claim Kit. Private request details are intentionally omitted._")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def read_json_input(path: Optional[str]) -> Dict[str, Any]:
    if path in {None, "-"}:
        text = sys.stdin.read()
    else:
        text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClaimError(f"input is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ClaimError("input JSON must be an object")
    return data


def command_init(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    if state_path.exists() and not args.force:
        raise ClaimError(f"state file already exists: {state_path} (use --force to replace it)")
    config = read_json_input(args.config)
    policy = dict(DEFAULT_POLICY)
    policy.update(config.get("policy", {}) or {})
    machines_in = config.get("machines", {}) or {}
    if not machines_in:
        raise ClaimError("config must define at least one machine")
    machines: Dict[str, Any] = {}
    for machine_id, machine in machines_in.items():
        machines[machine_id] = {
            "label": str((machine or {}).get("label", machine_id)),
            "active_claim": None,
            "updated_at": None,
        }
    seats = config.get("seats", {}) or {}
    if not seats:
        raise ClaimError("config must define at least one seat")
    now = parse_time(args.now)
    state = {
        "version": VERSION,
        "created_at": iso(now),
        "updated_at": iso(now),
        "policy": policy,
        "machines": machines,
        "seats": seats,
        "requests": [],
    }
    with state_lock(state_path):
        save_state(state_path, state)
        state["_now_override"] = iso(now)
        audit(state_path, state, "init", args.by, None, {"machines": list(machines), "seats": list(seats)})
    print(json.dumps({"ok": True, "state": str(state_path), "machines": list(machines), "seats": list(seats)}, indent=2))
    return 0


def command_template(args: argparse.Namespace) -> int:
    if args.format == "markdown":
        print("```panel-claim")
        print(f"Requester: {args.requester}")
        print(f"Machine: {args.machine}")
        print("Preference: undecided")
        print("Requested access: none")
        print("Public title: Short public description of the work")
        print("Private details: Details for the registrar only; never rendered to the board")
        print("Reason: What this machine time would make possible")
        print("Duration minutes: 60")
        print("Needed by: ")
        print("Proposed priority: normal")
        print("Can request: yes")
        print("Can self-launch: no")
        print("Can monitor: no")
        print("Can release: no")
        print("Owner approval ref: ")
        print("```")
        return 0
    template = {
        "requester": args.requester,
        "machine": args.machine,
        "preference": "undecided",
        "requested_access": "none",
        "public_title": "Short public description of the work",
        "private_details": "Details for the registrar only; never rendered to the board",
        "reason": "What this machine time would make possible",
        "duration_minutes": 60,
        "needed_by": "",
        "proposed_priority": "normal",
        "capabilities": {
            "can_request": True,
            "can_self_launch": False,
            "can_monitor": False,
            "can_release": False,
        },
        "owner_approval_ref": "",
    }
    print(json.dumps(template, indent=2))
    return 0


def command_submit(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    raw = read_json_input(args.input)
    now = parse_time(args.now)
    with state_lock(state_path):
        state = load_state(state_path)
        state["_now_override"] = iso(now)
        request = normalize_request(state, raw, now)
        state.setdefault("requests", []).append(request)
        save_state(state_path, state)
        audit(state_path, state, "submit", request["requester"], request["id"], {"status": request["status"], "machine": request["machine"]})
    print(json.dumps(request, indent=2))
    return 0


def command_parse_markdown(args: argparse.Namespace) -> int:
    text = sys.stdin.read() if args.input in {None, "-"} else Path(args.input).read_text(encoding="utf-8")
    print(json.dumps(parse_markdown_request(text), indent=2))
    return 0


def command_list(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state))
    rows = state.get("requests", [])
    if args.machine:
        rows = [r for r in rows if r.get("machine") == args.machine]
    if args.status:
        rows = [r for r in rows if r.get("status") == args.status]
    for request in rows:
        print(
            f"{request['id']}\t{request['status']}\t{request['machine']}\t"
            f"{request['requester']}\t{request['requested_access']}\t{request['public_title']}"
        )
    return 0


def command_approve(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    now = parse_time(args.now)
    with state_lock(state_path):
        state = load_state(state_path)
        state["_now_override"] = iso(now)
        request = find_request(state, args.request_id)
        if request["status"] != "requested":
            raise ClaimError(f"only a requested item can be approved (current status: {request['status']})")
        policy = state.get("policy", {})
        if policy.get("registrar_required", True) and not args.by:
            raise ClaimError("approve requires --by naming the registrar")
        if request["requested_access"] == "self_launch":
            if not policy.get("self_launch_enabled", False):
                raise ClaimError("self_launch is disabled by policy; approval cannot enable it through this command")
            if policy.get("owner_approval_required_for_self_launch", True) and not (args.owner_approval_ref or request.get("owner_approval_ref")):
                raise ClaimError("self_launch approval requires an owner approval reference")
        effective = args.effective_priority or request.get("proposed_priority") or "normal"
        if effective not in PRIORITIES:
            raise ClaimError(f"effective priority must be one of: {', '.join(PRIORITIES)}")
        request["status"] = "queued"
        request["effective_priority"] = effective
        request["approved_at"] = iso(now)
        request["approved_by"] = args.by
        request["decision_note"] = args.note or ""
        request["updated_at"] = iso(now)
        if args.owner_approval_ref:
            request["owner_approval_ref"] = args.owner_approval_ref
        claimed = False
        if args.claim_if_free:
            machine = get_machine(state, request["machine"])
            if not machine.get("active_claim"):
                promote_claim(state, request, args.by, now)
                claimed = True
        save_state(state_path, state)
        audit(state_path, state, "approve", args.by, request["id"], {"effective_priority": effective, "claimed": claimed})
    print(json.dumps(request, indent=2))
    return 0


def command_deny(args: argparse.Namespace) -> int:
    return _decision(args, "denied", "deny")


def command_withdraw(args: argparse.Namespace) -> int:
    return _decision(args, "withdrawn", "withdraw")


def _decision(args: argparse.Namespace, status: str, action: str) -> int:
    state_path = Path(args.state)
    now = parse_time(args.now)
    with state_lock(state_path):
        state = load_state(state_path)
        state["_now_override"] = iso(now)
        request = find_request(state, args.request_id)
        if request["status"] in {"claimed", "released"}:
            raise ClaimError(f"cannot {action} a request in status {request['status']}")
        request["status"] = status
        request["decision_note"] = args.note or ""
        request["updated_at"] = iso(now)
        save_state(state_path, state)
        audit(state_path, state, action, args.by, request["id"], {"note": args.note or ""})
    print(json.dumps(request, indent=2))
    return 0


def command_claim_next(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    now = parse_time(args.now)
    with state_lock(state_path):
        state = load_state(state_path)
        state["_now_override"] = iso(now)
        machine = get_machine(state, args.machine)
        if machine.get("active_claim"):
            raise ClaimError(f"machine {args.machine} already has an active claim: {machine['active_claim']}")
        queue = queue_for_machine(state, args.machine)
        if not queue:
            raise ClaimError(f"no queued requests for machine {args.machine}")
        request = queue[0]
        promote_claim(state, request, args.by, now)
        save_state(state_path, state)
        audit(state_path, state, "claim_next", args.by, request["id"], {"machine": args.machine})
    print(json.dumps(request, indent=2))
    return 0


def command_heartbeat(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    now = parse_time(args.now)
    with state_lock(state_path):
        state = load_state(state_path)
        state["_now_override"] = iso(now)
        request = find_request(state, args.request_id)
        if request["status"] != "claimed":
            raise ClaimError("only a claimed request can heartbeat")
        request["last_heartbeat_at"] = iso(now)
        if args.extend_minutes:
            base = parse_time(request.get("expires_at")) if request.get("expires_at") else now
            request["expires_at"] = iso(base + dt.timedelta(minutes=int(args.extend_minutes)))
        request["updated_at"] = iso(now)
        save_state(state_path, state)
        audit(state_path, state, "heartbeat", args.by, request["id"], {"extend_minutes": args.extend_minutes or 0})
    print(json.dumps(request, indent=2))
    return 0


def command_release(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    now = parse_time(args.now)
    with state_lock(state_path):
        state = load_state(state_path)
        state["_now_override"] = iso(now)
        request = find_request(state, args.request_id)
        if request["status"] != "claimed":
            raise ClaimError("only a claimed request can be released")
        machine = get_machine(state, request["machine"])
        if machine.get("active_claim") == request["id"]:
            machine["active_claim"] = None
            machine["updated_at"] = iso(now)
        request["status"] = "released"
        request["released_at"] = iso(now)
        request["updated_at"] = iso(now)
        request["decision_note"] = args.outcome or request.get("decision_note", "")
        save_state(state_path, state)
        audit(state_path, state, "release", args.by, request["id"], {"outcome": args.outcome or ""})
    print(json.dumps(request, indent=2))
    return 0


def command_expire(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    now = parse_time(args.now)
    changed: List[str] = []
    with state_lock(state_path):
        state = load_state(state_path)
        state["_now_override"] = iso(now)
        policy = state.get("policy", DEFAULT_POLICY)
        request_ttl = dt.timedelta(hours=float(policy.get("request_ttl_hours", 72)))
        queue_ttl = dt.timedelta(hours=float(policy.get("queue_ttl_hours", 168)))
        for request in state.get("requests", []):
            status = request.get("status")
            created = parse_time(request.get("created_at"))
            approved = parse_time(request.get("approved_at")) if request.get("approved_at") else created
            if status == "requested" and now - created >= request_ttl:
                request["status"] = "expired"
                request["updated_at"] = iso(now)
                changed.append(request["id"])
            elif status == "queued" and now - approved >= queue_ttl:
                request["status"] = "expired"
                request["updated_at"] = iso(now)
                changed.append(request["id"])
            elif status == "claimed" and request.get("expires_at") and now >= parse_time(request["expires_at"]):
                machine = get_machine(state, request["machine"])
                if machine.get("active_claim") == request["id"]:
                    machine["active_claim"] = None
                    machine["updated_at"] = iso(now)
                request["status"] = "expired"
                request["released_at"] = iso(now)
                request["updated_at"] = iso(now)
                changed.append(request["id"])
        save_state(state_path, state)
        audit(state_path, state, "expire", args.by, None, {"expired": changed})
    print(json.dumps({"expired": changed}, indent=2))
    return 0


def command_render_board(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state))
    text = render_board(state, args.machine)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Registrar-mediated panel machine claims (bookkeeping prototype).")
    parser.add_argument("--state", default="panel-claim-state.json", help="Path to the state JSON file.")
    parser.add_argument("--now", default=None, help="Override current time (ISO 8601); useful for tests and scheduled expiry checks.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Create a new state file from a config JSON document.")
    p.add_argument("--config", required=True, help="Config JSON path, or - for stdin.")
    p.add_argument("--by", default="registrar", help="Actor name for the audit log.")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=command_init)

    p = sub.add_parser("template", help="Print a request template.")
    p.add_argument("--requester", required=True)
    p.add_argument("--machine", required=True)
    p.add_argument("--format", choices=["json", "markdown"], default="json")
    p.set_defaults(func=command_template)

    p = sub.add_parser("submit", help="Validate and record a panel member's request or decline.")
    p.add_argument("--input", required=True, help="Request JSON path, or - for stdin.")
    p.set_defaults(func=command_submit)

    p = sub.add_parser("parse-markdown", help="Convert a Markdown panel-claim block to JSON.")
    p.add_argument("--input", required=True, help="Markdown path, or - for stdin.")
    p.set_defaults(func=command_parse_markdown)

    p = sub.add_parser("list", help="List requests.")
    p.add_argument("--machine")
    p.add_argument("--status", choices=REQUEST_STATUSES)
    p.set_defaults(func=command_list)

    p = sub.add_parser("approve", help="Registrar approval: move a requested item to the queue.")
    p.add_argument("request_id")
    p.add_argument("--by", required=True, help="Registrar identity.")
    p.add_argument("--effective-priority", choices=PRIORITIES)
    p.add_argument("--note", default="")
    p.add_argument("--owner-approval-ref", default="")
    p.add_argument("--claim-if-free", action="store_true", help="Immediately claim the machine if it is free.")
    p.set_defaults(func=command_approve)

    p = sub.add_parser("deny", help="Registrar denies a request.")
    p.add_argument("request_id")
    p.add_argument("--by", required=True)
    p.add_argument("--note", default="")
    p.set_defaults(func=command_deny)

    p = sub.add_parser("withdraw", help="Requester withdraws a request.")
    p.add_argument("request_id")
    p.add_argument("--by", required=True)
    p.add_argument("--note", default="")
    p.set_defaults(func=command_withdraw)

    p = sub.add_parser("claim-next", help="Promote the first queued request to an active claim.")
    p.add_argument("--machine", required=True)
    p.add_argument("--by", required=True)
    p.set_defaults(func=command_claim_next)

    p = sub.add_parser("heartbeat", help="Record activity for an active claim and optionally extend it.")
    p.add_argument("request_id")
    p.add_argument("--by", required=True)
    p.add_argument("--extend-minutes", type=int, default=0)
    p.set_defaults(func=command_heartbeat)

    p = sub.add_parser("release", help="Release an active claim.")
    p.add_argument("request_id")
    p.add_argument("--by", required=True)
    p.add_argument("--outcome", default="")
    p.set_defaults(func=command_release)

    p = sub.add_parser("expire", help="Expire stale requests, queued items, and claims whose end time has passed.")
    p.add_argument("--by", default="registrar")
    p.set_defaults(func=command_expire)

    p = sub.add_parser("render-board", help="Render a privacy-safe Markdown board snippet for one machine.")
    p.add_argument("--machine", required=True)
    p.add_argument("--output")
    p.set_defaults(func=command_render_board)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ClaimError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
