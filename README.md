# Meta Conversion

Configurable submitted-invoice CTWA Purchase reporting for Frappe v15.

## Setup and migration

Install ERPNext, Healthcare, CRM, sriaas_clinic, and wa_chat_hub first.
Run bench --site SITE migrate after updating this app, then restart workers
using your normal deployment procedure.

The first migration to configurable statuses preserves the existing go-live
cutoff, initializes Allowed Invoice Statuses to Paid, disables the integration,
and enables local test mode. Existing event records and the legacy token remain
stored; the legacy token is hidden and is no longer used. Subsequent migrations
preserve your configuration, including intentionally empty selections.

Open **Meta Conversion Settings**:
- Select Allowed Invoice Statuses: Paid, Partly Paid, Unpaid, and/or Overdue.
- Select the active Interakt Chat Channel Account containing the existing key.
- Select encounter types, sales types, and encounter places. All groups must match.
- Review Go Live, which filters by invoice creation time, not payment time.
- Enable processing in Local Test Mode and inspect Meta Conversion Events.

Selecting Unpaid includes both COD and prepaid invoices. There is no COD or
payment-category classification. Drafts, cancellations, return invoices,
non-positive values, and non-INR invoices are excluded regardless of selection.
Purchase value is the full rounded invoice total (grand total when appropriate),
not the deposit or cash collected. A later payment or shipment does not create
another Purchase for an already reported invoice.

## Account and attribution

The sender reads Chat Channel Account.interakt_api_key server-side. No separate
conversion token is needed. Requests are restricted to https://api.interakt.ai;
the account's message endpoint is not used as a conversion endpoint.

The source chain is Sales Invoice.source_encounter ->
Patient Encounter.sr_source_crm_lead -> CRM Lead.
The existing PEX attribution pair is preferred; lead attribution is the fallback.
A Chat Conversation must match the linked lead and both the click and source IDs.
All matching conversations must belong to the configured account. Missing or
ambiguous source accounts are skipped, never guessed from phone numbers.

The event freezes the account, attribution, invoice value, source links,
qualifying status, and filter configuration. Delivery rechecks current
eligibility and blocks changed source links or account selection. No changes
to WA Chat Hub or clinic schemas are required for these existing fields.

## Provider integration

The existing provider contract is retained:
POST /v1/public/track/conversions/ with Basic authentication, Purchase,
business_messaging, whatsapp, ad_id, ctwa_clid, INR/value, and partner_agent Haptik.

This contract has NOT been verified against the live Interakt account.
Confirm endpoint, payload, authentication, account entitlement, and target dataset
with Interakt before checking Provider Contract Confirmed and disabling test mode.
The public Event Track endpoint has a different payload and is not interchangeable.

Local Test Mode makes no API request and is not Meta Test Events. Legacy Pending
events without snapshots are also forced through a local test first.
HTTP 2xx means Provider Accepted only, not Meta receipt or attribution.
No outbound event ID is added until provider support is established.

Status/encounter filters do not establish whether health-derived events may be
shared. Assess external eligibility separately before enabling live delivery;
the app does not automatically classify clinical sensitivity.

## Processing and recovery

Submission/update hooks and a five-minute scan use the same eligibility rules.
One unique event per invoice and row locks protect local processing.
Skipped events are reconsidered when an invoice is evaluated again; Tested,
Failed, Accepted, Unknown, and Sending events are not automatically replayed.
A System Manager can explicitly re-evaluate Skipped, Tested, or Failed records.
Requalification records a new snapshot and observation timestamp.

Network failures and HTTP 5xx are Unknown. Interrupted Sending events require
provider reconciliation. No automatic ambiguous retries are performed.
The scan currently revisits qualifying invoices; incremental scanning is future
work. Event time is eligibility observation time, not a historical payment timestamp.
Refund corrections, split-invoice/amendment deduplication across invoice names,
and provider-side idempotency are not implemented.

## Verification

From the app directory, run:
    ../../env/bin/python -m unittest test_rules test_delivery -v

These are isolated tests, without database access or external requests.
After migration, run:
    bench --site SITE execute meta_conversion.checks.verify
