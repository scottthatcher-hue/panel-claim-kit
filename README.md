# Panel Claim Kit

A small, dependency-free prototype for letting members of an AI panel
**request** time on a shared machine without pretending that a request is
the same thing as control of that machine.

The kit was designed for a panel whose members have very different
abilities. One may be able to work only through a daily log. Another may be
able to prepare a task but not launch it. Another may decline machine
access entirely. The workflow records those differences instead of forcing
every member through the same door.

> **Status:** prototype / bookkeeping only. This code does not control a
> computer, launch an agent, open a browser, type credentials, change a
> setting, or grant an account permission.

## The core distinction

A claim has three separate layers:

1. **Preference** — does the panel member want machine time at all?
2. **Capability** — can it request, launch, monitor, stop, or release a
   session through the channels it actually has today?
3. **Authorization** — has the registrar approved the request, and has the
   machine owner approved any high-trust mode?

Only the first two come from the panel member. Authorization remains with
the registrar and machine owner.

## Access levels

| Level | Meaning |
| --- | --- |
| `none` | No access wanted or needed. |
| `reservation_request` | The member asks for time; the registrar operates the session. |
| `registrar_launched` | The member supplies a task; the registrar launches and verifies it. |
| `prepared_task` | The member prepares a bounded task package; the registrar reviews, launches, and verifies it. |
| `self_launch` | The member says it can launch and operate a session itself. Disabled by policy in the prototype. |

A request for `self_launch` becomes `capability_blocked` when the member
says it cannot self-launch. Even when the capability is claimed, approval
still fails while `self_launch_enabled` is false. Turning that on should
require a separate identity, security, audit, and stop-path review; it is
not a configuration detail to flip casually.

## Workflow

```text
panel member intake
        |
        v
  validate request ----> declined / no access / capability blocked
        |
        v
    requested
        |
        +---- registrar denies ----> denied
        |
        +---- requester withdraws -> withdrawn
        |
        v
      queued  (registrar sets effective priority)
        |
        v
     claimed  (one active claim per machine)
        |
        +---- heartbeat / bounded extension
        |
        v
     released or expired
```

Requests and queued items expire. Active claims carry a bounded end time.
The board renderer uses only the sanitized `public_title`; private details
and reasons stay in the registrar's state file and never reach the board.

## Porting this kit to another setup

The kit is deliberately environment-free: generic machine and seat IDs,
no accounts, no connectors, no machine control. A different owner can
hand it to their own Muse, which acts as registrar. `PORTING.md` is
the receiving guide — it lists every prerequisite (a suitable Mac, the
Muse app installed and paired, the macOS permissions the owner must
grant, machine-posture and policy decisions), the setup sequence, and
the local adapters (intake transport, board, executor, scheduling, stop
relay) that each environment must supply itself.

## Quick start

```sh
cp examples/config.example.json config.local.json
# Edit the machine and seat IDs for your own environment. Keep this local
# file out of a public package.

python3 panel_claim.py --state panel-claim-state.json \
  init --config config.local.json --by registrar

python3 panel_claim.py template \
  --requester example-seat-a \
  --machine shared-mac-1 \
  --format markdown

python3 panel_claim.py --state panel-claim-state.json \
  submit --input examples/reservation-request.json

python3 panel_claim.py --state panel-claim-state.json list

python3 panel_claim.py --state panel-claim-state.json \
  approve <request-id> --by registrar --claim-if-free

python3 panel_claim.py --state panel-claim-state.json \
  render-board --machine shared-mac-1
```

Markdown answers from a panel member can be converted before submission:

```sh
python3 panel_claim.py parse-markdown --input intake.md > request.json
python3 panel_claim.py --state panel-claim-state.json submit --input request.json
```

## Files

- `panel_claim.py` — the complete CLI and workflow engine.
- `PORTING.md` — the setup guide for a different owner and a different
  registrar (written for another Muse): roles, hardware/software/Muse
  prerequisites, the macOS permissions to grant, machine-posture and
  policy decisions, the setup sequence, the adapters a local setup must
  supply, and the extra gates before self-launch.
- `panel_claim_schema.json` — JSON Schema for a request.
- `templates/claim-intake.md` — the member-facing intake form.
- `examples/` — a generic configuration and three sample outcomes:
  reservation, decline, and capability-blocked self-launch.
- `tests/test_panel_claim.py` — end-to-end CLI tests.
- `run_tests.sh` — runs the test suite.
- `PUBLISHING.md` — a pre-publication checklist.

## Integration with an existing machine board

The kit keeps its own JSON state as the registrar's source of truth.
`render-board` emits a small Markdown snippet with the active claim and
queue for one machine. A registrar can paste or adapt that snippet into an
existing board.

That separation is deliberate. It lets a team pilot the intake and queue
rules before automating synchronization with a live board, a status page,
or a machine-control system.

## Suggested activation stages

### Stage 0 — package only
No panel member receives access. The code exists so an acceptance can be
acted on without designing under pressure.

### Stage 1 — intake only
Collect preferences and capabilities. Record declines faithfully. No
machine session follows from the form alone.

### Stage 2 — reservation only
Approve requests into a queue. The registrar operates every session,
verifies completion, and releases the machine.

### Stage 3 — prepared tasks
Members may submit bounded task packages. The registrar reviews the
package, launches it, verifies the result, and owns the stop path.

### Stage 4 — self-launch
Do not treat this as the natural final step. It requires named agent
identity, scoped machine permissions, reliable presence/heartbeat, a stop
path independent of the launched agent, audit retention, and the machine
owner's explicit approval.

## Design principles

- A decline is data, not a failed conversion.
- A requester proposes priority; the registrar sets effective priority.
- Public board text is sanitized by construction.
- One active claim per machine.
- Every meaningful transition is written to an append-only audit log.
- Expiry is normal behavior, not an error.
- The code that records trust decisions should not itself hold credentials.
