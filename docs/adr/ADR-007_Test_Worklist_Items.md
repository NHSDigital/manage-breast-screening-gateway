# ADR-007: Processing test worklist items

Date: 2026-07-20

Status: Accepted

## Context

When we deploy a new gateway instance to a hospital trust site, we need to ensure that worklist items will be processed correctly and that files can be uploaded to Rubie from within the hospital trust site.
We also want to avoid the overhead of having to set up a test clinic, appointment and accession number in Rubie as this will also require removal of records from a production system.

## Decision

We have added a test action which can be sent from the Rubie Admin UI to the gateway instance.

The action payload contains a test worklist item which will be processed by the gateway instance immediately.

The gateway instance will then send resulting emulated DICOM files back to Rubie.

These files contain sample images and test participant data. This allows us to verify that the gateway instance is processing worklist items correctly and that files can be uploaded to Rubie from within the hospital trust site.

The test action is marked as completed by Rubie and this is visible in the Rubie Admin UI in order to verify a successful test.
Any failures will be logged and visible in the Rubie Admin UI for investigation.

## Consequences

The relay connection to the gateway instance, along with internal processing of the test worklist item and gateway PACS storage, will be tested and verified.

All production authentication and authorisation methods will be used to ensure that the test action is processed correctly and that files can be uploaded to the Rubie API from within the hospital trust site.

This constitutes a full end-to-end test of the gateway instance and Rubie integration, without the need to set up a test clinic, appointment and accession number in Rubie and without the need to differentiate between test and production data in Rubie.
