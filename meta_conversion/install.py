import frappe
from meta_conversion.rules import SUPPORTED_STATUSES
from meta_conversion.compatibility import validate_schema, encounter_filter_values
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def setup():
    validate_schema(allow_missing_invoice_link=True)
    create_custom_fields({"Sales Invoice": [{"fieldname": "source_encounter", "label": "Source Encounter", "fieldtype": "Link", "options": "Patient Encounter", "insert_after": "customer", "read_only": 1}]}, update=False)
    for dt, field in [("Meta Encounter Type", "sr_encounter_type"), ("Meta Encounter Place", "sr_encounter_place")]:
        for value in encounter_filter_values(field):
            if value and not frappe.db.exists(dt, value):
                frappe.get_doc({"doctype": dt, "label": value}).insert(ignore_permissions=True)
    settings = frappe.get_single("Meta Conversion Settings")
    for value in sorted(SUPPORTED_STATUSES):
        if not frappe.db.exists("Meta Invoice Status", value):
            frappe.get_doc({"doctype": "Meta Invoice Status", "label": value}).insert(ignore_permissions=True)
    fresh = not settings.go_live
    if not settings.get("status_configuration_initialized"):
        if not settings.get("allowed_invoice_statuses"):
            settings.append("allowed_invoice_statuses", {"value": "Paid"})
        settings.go_live = settings.go_live or frappe.utils.now_datetime()
        settings.status_configuration_initialized = 1
        # Credential migration must never start live delivery automatically.
        settings.enabled = 0
        settings.test_mode = 1
        settings.provider_contract_confirmed = 0
        settings.provider_url = "https://api.interakt.ai"
        settings.save(ignore_permissions=True)
    if fresh:
        settings.go_live = frappe.utils.now_datetime()
        settings.test_mode = 1
        for value in ["Appointment", "Order"]:
            if frappe.db.exists("Meta Encounter Type", value):
                settings.append("encounter_types", {"value": value})
        settings.save(ignore_permissions=True)
