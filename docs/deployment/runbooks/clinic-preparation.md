# Clinic preparation

> **When to use**: Preparing for a live clinic (or a dummy run) that uses the
> gateway imaging flow. Work through it in order — the sections have lead times.

---

## The week before

- [ ] **Software currency**: the intended gateway release is deployed to the site VM
      (check the deploy pipeline history, or `current` junction target on the VM),
      and any Manage changes the clinic depends on are in prod.
- [ ] **Feature flag**: `gateway_images` is **on** for prod — it lives in
      **`flags.production.yml` in the Manage repo**.
- [ ] **Prod Manage records**: `Gateway` record with the machine's managed-identity
      OID; `Relay` record whose **Setting matches the clinic's Setting**.
- [ ] **Test data prepared with fresh accession numbers** — never reuse a previous
      clinic's CSV: Manage's per-gateway accession uniqueness rejects reused values,
      and gateway-side reuse serves stale participant data.
- [ ] **First time at a site, or after a promotion**: run a full remote dummy run
      first — one test participant end to end, glove-box exposure included.

## The day before

- [ ] **The VM is on and will stay on** — `az connectedmachine show … --query status`
      returns **Connected**.
- [ ] **The relay path passes traffic** — echo probe from the Manage container, or
      a fresh successful check-in.
- [ ] **Fresh appointments only** — any appointment that ever had manual image
      details recorded stays in manual mode by design.
- [ ] **Gateway worklist DB is clean** — no stale items from previous tests
      (`Get-GwWorklist`, or the run-command SELECT; wipe if needed).
- [ ] **People and access roster confirmed for the whole clinic window**:
  - someone with a **prod Rubie login** including Django admin (Gateway actions)
  - someone with **az / portal access** to the prod subscriptions
  - the **hospital contact** who can operate the modality and physically reach the VM
  - RDP to the VM if the hospital can provide it (live tails beat run-commands)
- [ ] **Fallback agreed**: if the gateway flow breaks mid-clinic, the manual-images
      flow carries the clinic and debugging happens without time pressure.
- [ ] **No stale Arc run-commands queued** on the machine
      (`az connectedmachine run-command list -o table`; delete non-terminal stragglers —
      they block deploys and diagnostics).

## The morning (~20 minutes before the first participant)

On the VM (RDP or run-command):

1. `Restart-Service Gateway-Relay` — fresh relay connection, freshly-started token
   clock. Wait for **`Connected - waiting for worklist actions...`** in the log.
2. `Get-GwHealth` — all four services **Running**, ports 104 and 11112 listening.
3. After the first (test) participant is checked in on Manage: `Get-GwWorklist`
   shows the item almost immediately — that proves Manage → Relay → VM
   end to end.
4. On the modality: query the worklist and confirm the participant is listed.

From a laptop:

1. `az relay hyco show … --query listenerCount` returns ≥ 1.
2. Gateway actions in the Django admin: the test check-in shows **`confirmed`**
   with an empty `last_error`.

## During the clinic — passive monitoring

On the VM, keep two windows open:

```powershell
Watch-GwLog PACS     # window 1 — see each C-STORE arrive
Watch-GwLog Upload   # window 2 — see each upload to Manage
```

Elsewhere: the **Gateway actions** admin page (each check-in → `confirmed`), and
App Insights **Live Metrics** if telemetry is up.

After each participant: `Get-GwImages` shows the expected image count with
`uploaded` equal to `images` within a minute or two.

## Afterwards

- [ ] Wipe test items from the gateway worklist DB; note any test studies/images
      created in prod Rubie and clean up or record them.
- [ ] Write up anything that surprised you — against this checklist — and fold the
      lesson back into this document. That is how everything above got here.
