# Incident review: Hull live clinic gateway failure, 6–7 July 2026

**Severity**: No patient impact. The clinic ran to completion on the manual-images fallback. Gateway (automatic) imaging was unavailable for the first live clinic; full end-to-end success was achieved the same afternoon.

## Summary
The first production use of the gateway imaging flow failed: worklist items sent from Rubie never reached the hospital gateway. Diagnosis was unusually hard because three independent faults were stacked, all producing the same symptom (a 30-second timeout on every send), and the system’s error reporting could not distinguish them. Each fault was peeled off in turn over ~36 hours; the full pipeline – check-in → worklist → modality → images → upload → Rubie – worked in production for the first time on the afternoon of 7 July.

## Symptoms
- Every worklist send from prod Rubie failed with a generic “Timeout waiting for response from gateway”; nothing appeared on the modality worklist.
- All infrastructure looked healthy: relay listener connected (count 1), managed identity and role assignments correct, gateway services running, config verified repeatedly on both sides.
- Independent probes succeeded where the app failed (a laptop-based relay echo round-tripped in 0.4s), deepening the confusion.

## Root causes
- **Private DNS blackhole**: the relay hostname resolved, inside the prod VNet, to the relay namespace’s private endpoint, which was silently broken despite showing *Approved* (later attributed to an Azure-side fault or provisioning race at PE creation; resolved weeks later by deleting and recreating the PE, which has worked since).
- **Runtime incompatibility**: the asyncio websockets client cannot reliably open connections inside gevent-patched gunicorn workers (DNS resolution via asyncio's thread executor degrades to 10s+, exhausting the connection budget). Every environment where sends had ever succeeded bypassed gevent (local dev, shell probes) – the production execution model had never actually been tested.
- **Silent listener death**: overnight, the gateway's relay connection died without the process noticing or the relay deregistering it – a “zombie” listener that looked connected while receiving nothing.

**Contributing factors**: relay send failures were recorded only in a database field, not logged; a single exception handler conflated “connection never opened” with “gateway never replied”; VM telemetry export was broken throughout, forcing diagnosis via remote commands; there was no admin visibility of gateway actions at the start of the incident.

## What we did
- Shipped diagnostic capability during the incident: a GatewayActions admin page.
- Built a standalone relay echo probe to test the relay → gateway path with Rubie removed; its container-side variant exposed the DNS/PE fault.
- Fixed DNS (interim public CNAME; later superseded by PE recreation), replaced the asyncio client with the synchronous websockets client ([Rubie ADR-009](https://github.com/NHSDigital/dtos-manage-breast-screening/blob/main/docs/adr/ADR-009-Synchronous_websockets_client_for_relay_sends.md)), and adopted a pre-clinic listener restart to clear zombie connections.
- Invoked the designed fallback: the clinic ran entirely on manual image recording, invisibly to participants.

## Improvements made since
- **Error reporting**: every relay failure now names its failing phase in both the admin and logs; unknown actions get structured error replies instead of silent connection closes.
- **Runbooks**: [clinic preparation](../deployment/runbooks/clinic-preparation.md) checklist; [live-clinic debugging](../deployment/runbooks/live-clinic-debugging.md); onboarding/promotion updates; diagnostic toolkit ships with the gateway release.
- **Automated end-to-end test participant**: a synthetic test can now be sent through the real production pipeline on demand – Rubie dispatches a test worklist item over the relay; the gateway stores it and invokes its modality emulator in place of the physical machine, which queries the worklist, generates DICOM images, and submits them through the standard PACS-and-upload path back to Rubie, where the round trip is confirmed against a dedicated test-action record (kept separate from clinical data).
- **Rehearsal practice**: successful remote dummy run completed ahead of the next live clinic.
- **In flight**: automated per-gateway healthcheck (health proven by traffic, surfaced in admin, wired into deploy pipelines); per-site imaging toggle so switching a site to manual is an audited admin action rather than an emergency deploy or record deletion; gateway listener liveness/token-renewal fixes.

## Learnings
- Health must be proven by traffic, not state. Listener counts, PE connection status, and service states each individually misled us during this incident. Everything we’ve built since sends a real message and judges the reply.
- The fallback earned its keep. Manual-images mode meant zero patient impact and removed all time pressure from diagnosis.
- Institutional knowledge belongs in the repo. Every finding was folded into version-controlled runbooks the same week, several of which were corrected again as evidence improved.
