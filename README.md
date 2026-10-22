# Meta Conversion

Frappe v15 app for invoice-only CTWA purchase reporting through Haptik.

Open **Meta Conversion Settings** using Desk search. Select encounter types,
sales types and encounter places. All filters must match. Start in local test
mode; this sends no requests. Inspect **Meta Conversion Event** records before
entering the provider base URL and Basic token and disabling test mode.

Only submitted, positive INR Sales Invoices with status Paid qualify. No Payment
Entry hooks or allocation checks are used. ERP Paid status is authoritative.
Returns and invoices created before the go-live cutoff are excluded. Invoice
hooks and a five-minute scheduled scan share the same per-invoice unique log.
Enable the site's scheduler and workers for processing.

The link chain is Sales Invoice.source_encounter → Patient
Encounter.sr_source_crm_lead → CRM Lead.sr_w_ctwa_clid and sr_w_source_id.
The clinic app already populates source_encounter when the field exists; this
app creates it if absent. Older or alternative billing paths without links are
logged as skipped, never inferred from remarks or phone numbers.

Value is rounded_total (or grand_total when rounding is disabled/unavailable).
Currency is INR. Event time is when eligibility was first observed, potentially
up to a scan interval after the status change. Provider payload uses Purchase,
business_messaging, whatsapp and partner_agent Haptik. Confirm with Haptik that
sr_w_source_id is the expected ad_id and verify its endpoint response contract
before enabling live delivery. HTTP 2xx means provider acceptance only.

Only System Managers can configure or re-evaluate events. Tokens are encrypted
by Frappe and neither payloads nor provider response bodies are logged. No
clinical data is sent. Test mode is local validation, not Meta Test Events.

Skipped, Tested and definitively Failed events support explicit Re-evaluate.
Network failures and HTTP 5xx are Unknown; interrupted Sending events also
require provider reconciliation. They are never automatically replayed because
provider idempotency support is unconfirmed. Accepted events are immutable to
normal users. Refunds after acceptance are not automatically reported.

Install: `bench get-app /path/to/meta_conversion` then
`bench --site SITE install-app meta_conversion`. Integration starts disabled.
