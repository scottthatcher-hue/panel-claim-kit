# Porting Guide — Setting This Kit Up With Another Muse

This guide is written for the receiving assistant (a Muse acting as
registrar) and the human who owns the shared machine. Work through it in
order. Do not skip the prerequisites: most failures with systems like this
are missing permissions or missing owner decisions, not missing code.

The kit itself is only the bookkeeping layer — intake, approval, queue,
claims, expiry, audit, and a privacy-safe board. Everything that touches a
real machine happens outside the kit, through the registrar, under the
machine owner's rules.

---

## 0. Roles to name before anything is installed

- **Machine owner** — the human who owns the shared computer and every
  account signed in on it. Only the owner grants permissions, approves
  high-trust modes, and can stop any session at any time.
- **Registrar** — the assistant (in the intended setup, a Muse) who runs
  this kit: collects requests, approves or denies them, claims and
  releases the machine, operates sessions, and reports back.
- **Panel members** — the other LLMs or assistants who may request time.
  Each one is a "seat" in the config. A seat never needs to run this code;
  it only needs a way to return the intake form.

Write these names down in your local config. Do not start with anonymous
or shared identities.

---

## 1. Hardware prerequisites

- [ ] **A Mac to share.** Any reasonably current Mac works. An always-on
  desktop (for example a Mac mini) is strongly recommended: laptops sleep,
  close, and travel, and a sleeping machine cannot be claimed.
- [ ] **Power:** the machine plugged in, ideally on a UPS if it is meant
  to be always available.
- [ ] **Network:** a stable connection on the owner's network. Note the
  machine's address or reservation if other systems need to reach it.
- [ ] **A display path:** a real display, or a deliberate headless setup
  the owner has tested. The owner also needs their own way to reach the
  machine when something needs a human hand (see §5).
- [ ] **Capacity:** enough free disk and memory for the work the panel
  will actually do. There is no universal number — check it against the
  intended tasks, not against this kit, which is tiny.

## 2. Software prerequisites on the shared Mac

- [ ] **macOS** on a currently supported release, with system updates
  kept current by the owner.
- [ ] **An admin account** the owner controls. Installing apps, changing
  permissions, and answering system prompts all need it, and those steps
  belong to the owner.
- [ ] **The browser(s) and apps the panel's work needs**, installed and
  signed in by the owner (for example, the browser profile where the
  web-based assistants are signed in). The kit signs in to nothing.
- [ ] **Python 3.9 or newer** available to the registrar's environment
  (`python3 --version`). The kit uses only the Python standard library —
  no packages to install.
- [ ] A way for the registrar to **run the CLI and keep its files**: a
  shell in the registrar's own environment, plus a private folder for the
  local config, the state file, and the audit log. These three files are
  local and must never be published or shared.

## 3. Muse prerequisites (the registrar's side)

- [ ] **A Muse account and the Muse app installed on the shared Mac**,
  signed in and paired by the owner, so the registrar Muse can reach
  the machine as a device.
- [ ] The machine shows **online** to Muse before any session is
  promised. A paired-but-asleep machine is not available.
- [ ] **Muse in Open at Login** on the Mac, with background activity
  allowed, so a reboot reconnects without the owner walking over.
- [ ] If the Muse app offers a **"keep this Mac awake"** option for
  computer use, the owner decides whether it is on — and understands it
  complements, but does not replace, the macOS sleep settings in §5.
- [ ] The owner present for the **pairing and permission approvals** the
  first time. Several of them cannot be granted remotely at all.

## 4. macOS permissions the owner must grant Muse on the shared Mac

Grant these in System Settings on the machine itself. Names vary slightly
between macOS releases; on recent releases the old "Accessibility" pane
may appear under a newer name such as "Device Control and Data Access,"
and screen capture under "Screen & System Audio Recording."

**Required for computer control (the registrar driving the machine):**

- [ ] **Accessibility / Device Control** — Muse listed and toggled ON.
  This is the input permission: without it the registrar can see the
  screen but cannot click or type. If input ever dies while the toggle
  looks on, the fix is local: toggle it off and back on at the machine,
  never over a remote session.
- [ ] **Screen Recording / Screen & System Audio Recording** — Muse
  listed and toggled ON. Without it the registrar is blind.
- [ ] **Full Disk Access** — Muse listed and toggled ON, needed for the
  file operations below and for many app data paths.

**Required for file work:**

- [ ] **Filesystem read/write access** for the folders the registrar will
  actually use (Desktop, Downloads, Documents, or a dedicated shared
  folder). Scope it to the work; the kit's own state folder must be
  registrar-only.

**Grant only if the panel's channels use them:**

- [ ] **Apple Mail, Notes, and Messages access/automation** — if a seat
  is reached through the owner's mail, notes, or messages.
- [ ] **Calendar, Contacts, Reminders** — per-data-source grants. These
  typically appear only after the app requests access, and the owner
  clicks Allow on the prompt; there may be no "add" button in Settings.
  Skip them entirely if the panel does not use them.
- [ ] **Notifications allowed for Muse**, so approval requests and
  alerts are visible to the owner.
- [ ] Any **per-app permissions** for specific apps the registrar must
  drive (screen capture and input are global; some apps ask separately
  for their own data).

**Known walls to plan around (observed behaviour, not kit bugs):**

- System **password prompts, passkey sheets, and password-manager apps**
  generally cannot be driven through a remote control channel. The owner
  should expect to type their Mac password or tap a passkey prompt in
  person (or through their own remote-desktop session) when an install or
  a sign-in demands it.
- A **locked or asleep** Mac cannot be driven. See §5.
- Some surfaces may be outside the control channel entirely (on the
  reference setup: Terminal and Script Editor are not drivable, and
  menu-bar status menus cannot be clicked). Test the apps your panel
  needs before promising a seat that route.

## 5. Machine posture — owner decisions to make explicitly

Defaults are how shared machines get into trouble. The owner should
decide, and write down:

- [ ] **Sleep policy:** whether the machine may sleep, and if it must
  stay available, the macOS settings that keep it awake (display sleep,
  automatic sleeping, wake for network access).
- [ ] **Recovery after power loss:** "start up automatically after a
  power failure" on or off; and if unattended recovery matters, the
  auto-login decision — noting the real trade-off: auto-login usually
  means FileVault off, i.e. no encryption at rest. That is the owner's
  call to make knowingly, not a default to inherit.
- [ ] **Screen lock policy:** how quickly the screen locks and whether a
  password is required — balanced against the fact that a locked machine
  blocks the registrar.
- [ ] **A human reach path:** how the owner gets to the machine for the
  steps only they can do (physically, or their own remote desktop).
  Passkey and credential steps are in-person by design.
- [ ] **One user session:** the work happens in the owner's signed-in
  session. Other people's sessions and data do not belong on a shared
  panel machine.
- [ ] **Update policy:** who runs macOS and app updates, and when, so an
  update reboot never silently strands a claimed session.

## 6. Accounts and channels prerequisites (per panel member)

The kit provides **no connectors**. For each seat, the registrar needs a
working way to (a) deliver the intake form, (b) receive the answer, and
(c) report the outcome. Examples of routes that can work, depending on
what the owner has:

- A signed-in web session in the shared Mac's browser.
- A native app on the shared Mac.
- A shared document or folder both sides can read/write.
- A daily log or notes channel the seat already maintains.
- A messaging channel, where automation permission actually allows
  sending — test it; "should work" channels that silently fail are the
  most common cause of a seat being wrongly reported as unresponsive.

For every seat, record in the local config: its stable ID, display name,
and its channel(s). A seat with no working channel is recorded as
**unreachable**, never simulated. The registrar also needs the owner's
accounts for any service a session will use — signed in by the owner, on
the shared machine, ahead of time. No credential of any kind goes into
this kit, its config, its state, or a request.

## 7. Process and policy prerequisites (decide before the first claim)

- [ ] **Claim etiquette:** check the board *and* the live machine state
  before driving (the board shows intent; only a live check shows
  activity). One driver at a time. Claim before the first control action;
  release when the session ends, with start and end times recorded.
- [ ] **Stale claims:** how old a claim may get, with no live activity
  behind it, before the registrar may clear it — and how that clearing is
  noted.
- [ ] **Priority:** requesters propose; the registrar sets effective
  priority; the owner arbitrates disputes and can re-prioritize at any
  time. Priority never interrupts a live session without an explicit
  stop order from the owner.
- [ ] **Durations and expiry:** default and maximum claim length,
  request and queue lifetimes. (The kit ships with 60-minute default /
  240-minute maximum / 72-hour request / 168-hour queue lifetimes —
  adjust deliberately.)
- [ ] **Stop path:** how the owner stops a session (a word to the
  registrar is enough in the registrar-operated stages), and how a stop
  is relayed if work is running in more than one place.
- [ ] **Scope limits:** task types that are out of bounds for panel
  sessions (for example: anything involving credentials, payments,
  health data, or other people's private information), written down
  before the first request arrives.
- [ ] **Board privacy:** public titles are sanitized, short, and safe to
  display. Private details never reach the board — the kit enforces this
  in its renderer; keep it true in any board you sync by hand.
- [ ] **Audit:** where the kit's audit log lives, who may read it, and
  how long it is kept.

## 8. Setup sequence for the receiving Muse

1. Read `README.md` and this guide in full before running anything.
2. Run the tests: `./run_tests.sh` — all tests must pass.
3. Copy `examples/config.example.json` to a **local, unpublished**
   config; replace the example machine and seat IDs with the real ones
   from §0 and §6.
4. Initialise state in a private location:
   `python3 panel_claim.py --state <private-path> init --config <local-config> --by <registrar-id>`
5. Dry-run the three examples (reservation, decline, capability-blocked
   self-launch) against a throwaway state file and confirm the outcomes
   match `README.md`.
6. Decide where the board lives (a file the owner can see; optionally a
   status display) and how `render-board` output reaches it — by hand at
   first.
7. Start at **Stage 1 (intake only)**: collect preferences and
   capabilities. No machine session follows from a form alone.
8. Move to Stage 2/3 only when the owner says so. Leave
   `self_launch_enabled` **false**.

## 9. Adapters you must supply locally

| Function | Kit provides | You supply |
| --- | --- | --- |
| Intake delivery/collection | The form + Markdown/JSON formats | The transport per seat (§6) |
| Approval & queue | Full workflow in the CLI | The registrar's judgement and the owner's rules (§7) |
| Board/status display | `render-board` Markdown snippet | The board itself and the sync step |
| Machine operation | Nothing — by design | The registrar's own computer-control session, claimed first |
| Scheduling | Expiry logic (`expire` command) | A timer/schedule that runs it, and heartbeat reminders |
| Stop relay | Statuses and audit entries | The actual stop: owner → registrar → running session |
| Reporting | State + audit log to report from | The message to the owner, in the owner's preferred form |

## 10. Extra prerequisites before ever enabling self-launch (Stage 4)

Do not treat self-launch as a configuration flip. It additionally needs:

- A **named, individual identity** for the launching agent (no shared or
  anonymous claimants).
- **Scoped machine permissions** for that identity, granted by the owner.
- A **reliable presence/heartbeat** so a live claim is distinguishable
  from an abandoned one.
- A **stop path independent of the launched agent** — if the agent is
  the only thing that can stop itself, there is no stop path.
- **Audit retention** the owner has reviewed.
- The owner's **explicit approval**, recorded, for that agent and that
  mode.

Until all six exist, a seat that asks for self-launch gets
`registrar_launched` or `prepared_task` instead — or an honest
`capability_blocked`.

## 11. Minimum viable pilot checklist

- [ ] Owner, registrar, and seats named (§0)
- [ ] Shared Mac online, plugged in, reachable (§1, §5)
- [ ] Muse app installed, paired, Open at Login (§3)
- [ ] Accessibility/Device Control + Screen Recording + Full Disk Access
  granted and *tested with one short control session* (§4)
- [ ] One working channel per seat, tested end-to-end (§6)
- [ ] Claim etiquette, durations, stop path, and scope limits written
  down (§7)
- [ ] Tests pass; local config and state created and kept private (§8)
- [ ] Stage 1 intake collected, including at least one honest decline
  or unreachable recorded as itself

If every box is checked, the panel can start reserving machine time with
the registrar operating every session — which is as far as this kit, on
its own, should ever take a new setup.
