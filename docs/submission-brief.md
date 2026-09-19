# Averis: shipping document review

**Team GoodLord:** Aung Phone Khant, Ella, Pei En and Congye.

[Try the app](https://averis-hackathon-production.up.railway.app/) · [Source code](https://github.com/Morris-Zin/Averis-Hackathon)

## Problem and product

Shipping staff receive document checks, new shipping instructions, invoice questions, operational updates and spam in one inbox. Before a draft Bill of Lading is finalized, its shipment details must agree with the Shipping Instruction.

Averis classifies these five kinds of messages and brings document checks into a familiar review queue. It compares seven fields: shipper, consignee, notify party, loading port, discharge port, container count and gross weight. Every finding links to its source. Reliable mismatches enter the mismatch queue automatically; uncertain readings remain visible for review.

Employees can change a category, choose a document pair, correct a reading, assign a case and attach a revised draft. Correcting our extraction does not edit the original document. Completing a review does not remove an unresolved shipment discrepancy.

## Architecture and integration

The monorepo contains a Next.js static frontend and a Python FastAPI application. Railway runs the public application and a separate private worker. Neon PostgreSQL stores cases, revisions, sessions, durable processing runs and the AI spending ledger. A private Cloudflare R2 bucket stores original documents.

Jev selects categories and source evidence from prepared text. Format readers handle TXT, native PDF, ordinary DOCX, bounded XLSX and English scans. Deterministic code parses quantities, converts explicit units and compares SI and BL values. Each document is read independently, so the BL extractor never receives the SI's expected values.

Deep modules keep document parsing, provider decisions, shipment verification, workflow and durable processing behind domain operations. The frontend consumes generated API types and backend decisions instead of duplicating comparison rules.

## Reliability and limits

Processing uses persisted checkpoints, leases and attempt tokens. Duplicate delivery does not repeat completed stages; stale results cannot overwrite current revisions. Reviewer mutations use optimistic concurrency checks. All paid requests reserve funds through the same budget authority, including evaluation requests; uncertain charges retain their reservations.

Public visitors receive isolated, temporary demo workspaces with controlled synthetic examples. Arbitrary uploads require operator authorization. Original files remain private and every file request checks workspace access. Reviewer names are simulated identities, not production authentication.

Confidence is not an accuracy guarantee. OCR quality and model confidence are separate checks. Missing values, missing units, conflicting document identities and unsupported structures cannot become matches. Resource limits include 10 MB per attachment, 20 PDF pages and three OCR pages per document.

## Validation and lessons

See [validation evidence](validation.md) and [evaluation results](evaluation-results.md) for measured results and their scope. Offline CI covers domain rules, real PostgreSQL transactions, workspace isolation, revisions, retries, budget races and generated API contracts. Browser checks exercise the deployed review workflow.

Development evaluation exposed both implementation defects and organizer-label disagreements. Reader fixes preserve complete field evidence and prevent noisy OCR from becoming confident discrepancies. Some source emails have no attachments even though the organizer expects an OK document check; Averis reports missing attachments instead of fabricating a successful comparison. Coverage and abstentions therefore accompany accuracy figures.

The current system is a working prototype. It does not claim measured enterprise capacity or production identity security. No reduction in employee handling time has yet been measured.

## Next steps

Add production authentication and mailbox connectors, measure throughput and recovery under load, and evaluate Malay and Mandarin through the document-reading and inference boundaries. Expand format support only with source-location and uncertainty tests. Measure employee review time and missed discrepancies in a controlled operational pilot.
