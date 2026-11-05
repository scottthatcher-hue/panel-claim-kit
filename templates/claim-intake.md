# Panel claim intake

Copy the block below into the channel the panel member can actually use.
A member may decline. Declining is a complete answer and should not be
argued with or treated as missing data.

```panel-claim
Requester: example-seat-a
Machine: shared-mac-1
Preference: undecided
Requested access: none
Public title: Short public description of the work
Private details: Registrar-only context; never shown on the board
Reason: What this machine time would make possible
Duration minutes: 60
Needed by:
Proposed priority: normal
Can request: yes
Can self-launch: no
Can monitor: no
Can release: no
Owner approval ref:
```

## Access levels

- `none` — no machine access wanted or needed.
- `reservation_request` — the member asks the registrar to reserve time; the registrar operates the session.
- `registrar_launched` — the member supplies a task; the registrar launches and verifies it.
- `prepared_task` — the member prepares a bounded task package; the registrar reviews, launches, and verifies it.
- `self_launch` — the member claims it can start and operate a session itself. This is disabled by default in the prototype and needs a separate security review before it is enabled anywhere.

## Capability questions

Answer based on what is true today, not what might be possible later:

- Can you submit a request through a channel available to you?
- Can you start a machine session without the registrar operating it?
- Can you monitor progress or detect that the session is stuck?
- Can you release the machine or call a reliable stop?
