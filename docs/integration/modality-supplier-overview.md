# Integrating a mammography modality with the Rubie gateway

> **Audience**: imaging equipment suppliers (modality vendors and their service engineers) asked to configure a mammography unit to work with the NHS **Manage Breast Screening** service ("Rubie"). It describes what the integration involves so suppliers can scope and cost the work. Site-specific values (IP addresses, AE titles, ports) are supplied separately for each trust.

## Background

Rubie is an NHS England service that manages breast screening clinics. To connect it to imaging equipment, a small **gateway** is installed on a trust-provided Windows virtual machine on the hospital network. The gateway presents standard DICOM services to the modality.

No supplier software is installed and no connection is made to supplier systems. The entire integration is configuration on the modality: adding the gateway as a worklist source and as an additional image destination.

## What the gateway provides

| Service | DICOM role | Purpose |
| ------- | ---------- | ------- |
| Worklist | MWL SCP (C-FIND, Modality Worklist Information Model) | Scheduled screening appointments appear on the unit's worklist as participants are checked in |
| Performed procedure | MPPS SCP (N-CREATE / N-SET), on the worklist node | The unit reports the procedure complete or discontinued |
| Image receipt | Storage SCP (C-STORE) | The unit sends acquired images to the gateway as an additional archive destination |

### Notes

- Worklist entries carry patient name, patient ID, accession number, scheduled procedure step date/time, modality (`MG`) and a requested procedure description. Responses use the UTF-8 character set (`ISO_IR 192`).
- Image receipt accepts only the two 2D digital mammography SOP classes (Digital Mammography X-Ray Image Storage – For Presentation and – For Processing). Other SOP classes are rejected at association negotiation, so the archive destination should be configured to send 2D mammography images only.
- The trust's clinical PACS is unaffected. The gateway is an *additional* destination; the unit keeps sending full-fidelity images to the trust PACS. The gateway keeps only reduced-resolution copies for display within the Rubie web application — it is not a clinical archive.
- Calling AE titles are allowlisted. The gateway only accepts associations from calling AE titles registered with the programme in advance, so each unit must use a fixed, agreed calling AE title.

## Configuration required on each unit

Once the gateway VM is in place at a site, the modality-side work is:

1. **Add a worklist (MWL) node** — called AE title, hostname/IP and port as supplied for the site.
2. **Add an archive (store) node** on the same host (separate port), and include it in the unit's auto-send/auto-route so acquired 2D mammography
   images go to both the trust PACS and the gateway.
3. **Enable MPPS to the worklist node** so completion status is reported (used to close out the appointment; optional but preferred where the unit
   supports it).
4. Set the agreed calling AE title for the unit and confirm it with the programme before go-live.
5. Verification session (typically under an hour, can be remote with the trust's help): DICOM echo to both nodes, a test worklist query, a test
   exposure sent end to end.

## Network

The modality and the gateway VM sit on the same hospital network; no supplier-to-cloud or modality-to-internet connectivity is introduced. DICOM traffic between the unit and the gateway is unencrypted (as is typical for intra-hospital DICOM) and never leaves the hospital network; the gateway's own connection to NHS cloud services is outbound-only from the VM. Trust firewall rules may need to permit the modality-to-gateway ports — this is handled with the trust, not the supplier.

## What we ask suppliers to provide

For rollout planning we would like, per unit model:

- confirmation that **MWL query, MPPS and multiple archive destinations** are available/licensed on the deployed fleet, and the cost where they are not;
- the **cost of the configuration work** described above, remote and on-site, per unit;
- availability and cost of an engineer (or remote support) for the **verification session**;
- the **ongoing support model** for subsequent configuration changes (e.g. an AE title or address change when a unit moves).

## Further technical detail

The gateway is open source. Suppliers who want more depth can read the [architecture overview](../architecture.md), the [MWL server documentation](../mwl/README.md) and the [PACS (storage) server documentation](../pacs/README.md) in this repository.
