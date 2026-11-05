# Publishing checklist

This package is designed to be publishable as a small code repository or
Gist, but do not publish a working local copy without checking it first.

## Remove local material

- [ ] No real `config.local.json`.
- [ ] No real state file (`*.json` created by `init`) or audit log (`*.audit.jsonl`).
- [ ] No machine addresses, account names, email addresses, private URLs, client names, health details, credentials, tokens, approval references, or private task details.
- [ ] Example names are generic and do not identify a real panel member's private channels.
- [ ] Public titles in examples are safe to display.
- [ ] `PORTING.md` still describes prerequisites generically — no local machine names, permission states, network details, or setup history from the environment it was written in.

## Verify behavior

- [ ] `python3 -m unittest discover -s tests -v` passes.
- [ ] A reservation can be submitted, approved, claimed, and released.
- [ ] A decline remains a decline and never enters the queue.
- [ ] A self-launch request without the capability becomes `capability_blocked`.
- [ ] A self-launch approval fails while `self_launch_enabled` is false.
- [ ] The rendered board omits `private_details` and `reason`.
- [ ] Expiry frees a machine with an expired active claim.

## Publication notes

- [ ] State clearly that this is bookkeeping/prototype code, not a remote-control system.
- [ ] Keep the version number in `panel_claim.py` and this package in sync.
- [ ] Choose a license before presenting it as reusable open-source software.
- [ ] Include the test file; the safety gates are easier to trust when the tests travel with the code.
- [ ] Do not add screenshots or sample output from a live board unless the public titles and identities have been reviewed.
