import json
from datetime import timezone

import frappe
import requests
from frappe.utils import get_datetime, now_datetime

from meta_conversion.rules import amount, eligible, selected_statuses
from meta_conversion.provider import get_account, validate_origin


def invoice_changed(doc, method=None):
    if doc.docstatus == 1:
        frappe.enqueue("meta_conversion.api.evaluate", invoice_name=doc.name, enqueue_after_commit=True)


def scan():
    settings = frappe.get_single("Meta Conversion Settings")
    if not settings.enabled or not settings.go_live or not selected_statuses(settings):
        return
    # Keyset pages avoid starving newer invoices behind previously examined records.
    cursor = ""
    while True:
        rows = frappe.get_all("Sales Invoice", filters={"docstatus": 1, "status": ["in", sorted(selected_statuses(settings))], "creation": [">=", settings.go_live], "name": [">", cursor]}, pluck="name", order_by="name", limit_page_length=500)
        if not rows:
            break
        for name in rows:
            evaluate(name)
        cursor = rows[-1]
    for name in frappe.get_all("Meta Conversion Event", filters={"status": "Pending"}, pluck="name", limit_page_length=500):
        frappe.enqueue("meta_conversion.api.deliver", event_name=name, enqueue_after_commit=True)


def context(invoice_name, settings, snapshot=None):
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    if not settings.go_live or get_datetime(invoice.creation) < get_datetime(settings.go_live):
        return invoice, None, None, "Invoice predates go-live"
    encounter_name = invoice.get("source_encounter")
    if not encounter_name:
        return invoice, None, None, "Missing source encounter"
    encounter = frappe.get_doc("Patient Encounter", encounter_name)
    selections = {field: {r.value for r in settings.get(table)} for field, table in [("sr_encounter_type", "encounter_types"), ("sr_sales_type", "sales_types"), ("sr_encounter_place", "encounter_places")]}
    reason = eligible(invoice.as_dict(), encounter.as_dict(), selections, selected_statuses(settings))
    if reason:
        return invoice, encounter, None, reason
    if not encounter.get("sr_source_crm_lead"):
        return invoice, encounter, None, "Missing source CRM lead"
    lead = frappe.get_doc("CRM Lead", encounter.sr_source_crm_lead)
    if snapshot and (snapshot.get("encounter") != encounter.name or snapshot.get("crm_lead") != lead.name):
        return invoice, encounter, lead, "Source links changed after qualification"
    if not snapshot:
        # PEX already copies these fields; prefer its transaction-specific pair.
        if encounter.get("sr_w_ctwa_clid") and encounter.get("sr_w_source_id"):
            lead.sr_w_ctwa_clid = encounter.sr_w_ctwa_clid
            lead.sr_w_source_id = encounter.sr_w_source_id
    if snapshot:
        lead.sr_w_ctwa_clid = snapshot.get("ctwa_clid")
        lead.sr_w_source_id = snapshot.get("ad_id")
    if not lead.get("sr_w_ctwa_clid") or not lead.get("sr_w_source_id"):
        return invoice, encounter, lead, "Missing CTWA click or ad identifier"
    if not settings.get("channel_account"):
        return invoice, encounter, lead, "Missing Interakt Chat Channel Account"
    if snapshot:
        if snapshot.get("channel_account") != settings.channel_account:
            return invoice, encounter, lead, "Source account does not match configured account"
    else:
        conversations = frappe.get_all("Chat Conversation", filters={
            "linked_crm_lead": lead.name,
            "ctwa_clid": lead.sr_w_ctwa_clid,
            "source_id": lead.sr_w_source_id,
        }, fields=["name", "channel_account"], limit_page_length=0)
        accounts = {row.channel_account for row in conversations}
        if accounts != {settings.channel_account}:
            return invoice, encounter, lead, "Missing, ambiguous, or mismatched source conversation account"
        lead.conversion_conversation = sorted(row.name for row in conversations)[0]
    return invoice, encounter, lead, ""


def evaluate(invoice_name):
    settings = frappe.get_single("Meta Conversion Settings")
    if not settings.enabled:
        return
    existing = frappe.db.get_value("Meta Conversion Event", {"sales_invoice": invoice_name}, ["name", "status"], as_dict=True)
    if existing:
        if existing.status == "Skipped":
            _requalify(existing.name, settings, automatic=True)
        return
    invoice, encounter, lead, reason = context(invoice_name, settings)
    if reason == "Invoice predates go-live":
        return
    event = frappe.get_doc({"doctype": "Meta Conversion Event", "sales_invoice": invoice.name, "encounter": encounter.name if encounter else None, "crm_lead": lead.name if lead else None, "status": "Skipped" if reason else "Pending", "detail": reason, "amount": amount(invoice.as_dict()), "qualified_at": now_datetime(), "test_mode": settings.test_mode})
    if not reason:
        _snapshot(event, invoice, encounter, lead, settings)
    frappe.db.savepoint("meta_conversion_insert")
    try:
        event.insert(ignore_permissions=True)
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        frappe.db.rollback(save_point="meta_conversion_insert")
        return
    if not reason:
        frappe.enqueue("meta_conversion.api.deliver", event_name=event.name, enqueue_after_commit=True)


def deliver(event_name):
    settings = frappe.get_single("Meta Conversion Settings")
    if not settings.enabled:
        return
    frappe.db.sql("select name from `tabMeta Conversion Event` where name=%s for update", event_name)
    event = frappe.get_doc("Meta Conversion Event", event_name)
    if event.status != "Pending":
        return
    invoice, encounter, lead, reason = context(event.sales_invoice, settings, json.loads(event.attribution_snapshot) if event.attribution_snapshot else None)
    if reason:
        event.status, event.detail = "Skipped", reason
        event.save(ignore_permissions=True)
        return
    if not event.attribution_snapshot:
        _snapshot(event, invoice, encounter, lead, settings)
        event.test_mode = 1
    if event.test_mode or settings.test_mode:
        event.status, event.detail = "Tested", "Eligibility verified locally; no request sent. Re-evaluate explicitly for production."
        event.save(ignore_permissions=True)
        return
    if not settings.provider_contract_confirmed:
        event.status, event.detail = "Failed", "Interakt conversion API contract is not confirmed"
        event.save(ignore_permissions=True)
        return
    origin = validate_origin(settings.provider_url)
    account = get_account(settings, require_key=True)
    token = account.get_password("interakt_api_key")
    # Frappe datetimes are site-local; convert to UTC before Unix serialization.
    import pytz
    local = pytz.timezone(frappe.utils.get_system_timezone())
    timestamp = int(local.localize(get_datetime(event.qualified_at)).astimezone(timezone.utc).timestamp())
    payload = {"data": [{"event_name": "Purchase", "event_time": timestamp, "action_source": "business_messaging", "messaging_channel": "whatsapp", "user_data": {"ad_id": lead.sr_w_source_id, "ctwa_clid": lead.sr_w_ctwa_clid}, "custom_data": {"currency": "INR", "value": event.amount}}], "partner_agent": "Haptik"}
    event.status, event.detail = "Sending", "Dispatch started; interrupted requests require provider reconciliation."
    event.save(ignore_permissions=True)
    frappe.db.commit()  # durable claim; never automatically replay an ambiguous request
    try:
        response = requests.post(origin + "/v1/public/track/conversions/", headers={"Authorization": "Basic " + token}, json=payload, timeout=(10, 30), allow_redirects=False)
        code = response.status_code
        status = "Provider Accepted" if 200 <= code < 300 else ("Unknown" if code >= 500 else "Failed")
        detail = f"HTTP {code}. Provider acceptance does not establish Meta attribution."
    except requests.RequestException:
        status, detail = "Unknown", "Network failure; check provider before retrying to avoid duplicate purchases."
    frappe.db.set_value("Meta Conversion Event", event.name, {"status": status, "detail": detail})


def _snapshot(event, invoice, encounter, lead, settings):
    event.channel_account = settings.channel_account
    event.source_conversation = lead.get("conversion_conversation")
    event.invoice_status = invoice.status
    event.amount = amount(invoice.as_dict())
    event.qualified_at = now_datetime()
    event.attribution_snapshot = json.dumps({
        "channel_account": settings.channel_account,
        "encounter": encounter.name, "crm_lead": lead.name,
        "ad_id": lead.sr_w_source_id, "ctwa_clid": lead.sr_w_ctwa_clid,
    })
    event.configuration_snapshot = json.dumps({
        "allowed_invoice_statuses": sorted(selected_statuses(settings)),
        **{key: sorted(row.value for row in settings.get(key))
           for key in ("encounter_types", "sales_types", "encounter_places")},
    })


def _requalify(event_name, settings, automatic=False):
    table = "`tabMeta Conversion Event`"
    frappe.db.sql("select name from " + table + " where name=%s for update", event_name)
    event = frappe.get_doc("Meta Conversion Event", event_name)
    allowed = ("Skipped",) if automatic else ("Skipped", "Tested", "Failed")
    if event.status not in allowed:
        if automatic:
            return
        frappe.throw("Only skipped, tested, or definitively failed events can be re-evaluated.")
    invoice, encounter, lead, reason = context(event.sales_invoice, settings)
    if reason:
        if automatic:
            return
        frappe.throw(reason)
    event.encounter, event.crm_lead = encounter.name, lead.name
    _snapshot(event, invoice, encounter, lead, settings)
    event.status, event.detail, event.test_mode = "Pending", "", settings.test_mode
    event.save(ignore_permissions=True)
    frappe.enqueue("meta_conversion.api.deliver", event_name=event.name, enqueue_after_commit=True)


@frappe.whitelist()
def reevaluate(event_name):
    frappe.only_for("System Manager")
    settings = frappe.get_single("Meta Conversion Settings")
    if not settings.enabled:
        frappe.throw("Enable Meta Conversion before re-evaluating.")
    _requalify(event_name, settings)
