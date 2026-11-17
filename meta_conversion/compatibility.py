"""Validate the data contract, independent of the clinic application's name."""
import frappe

TEXT_TYPES = ("Data", "Small Text", "Text", "Long Text")
# Optional encounter attribution copies are not required: the sender has a lead fallback.
REQUIRED_FIELDS = {
    "Sales Invoice": {
        "source_encounter": ("Link", "Patient Encounter"),
    },
    "Patient Encounter": {
        "sr_source_crm_lead": ("Link", "CRM Lead"),
        "sr_encounter_type": (("Select", "Link"), None),
        "sr_encounter_place": (("Select", "Link"), None),
        "sr_sales_type": ("Link", "SR Sales Type"),
    },
    "CRM Lead": {
        "sr_w_ctwa_clid": (TEXT_TYPES, None),
        "sr_w_source_id": (TEXT_TYPES, None),
    },
    "Chat Conversation": {
        "channel_account": ("Link", "Chat Channel Account"),
        "linked_crm_lead": ("Link", "CRM Lead"),
        "ctwa_clid": (TEXT_TYPES, None),
        "source_id": (TEXT_TYPES, None),
    },
    "Chat Channel Account": {
        "interakt_api_key": ("Password", None),
        "channel_type": ("Select", None),
        "is_active": ("Check", None),
    },
}


def inspect_schema(allow_missing_invoice_link=False):
    errors = []
    for doctype, fields in REQUIRED_FIELDS.items():
        if not frappe.db.exists("DocType", doctype):
            errors.append("Missing DocType: " + doctype)
            continue
        meta = frappe.get_meta(doctype)
        for name, (types, target) in fields.items():
            df = meta.get_field(name)
            if not df:
                if allow_missing_invoice_link and doctype == "Sales Invoice" and name == "source_encounter":
                    continue
                errors.append("Missing field: " + doctype + "." + name)
                continue
            allowed = (types,) if isinstance(types, str) else types
            if df.fieldtype not in allowed:
                errors.append(doctype + "." + name + " must be " + " or ".join(allowed))
                continue
            if target and df.options != target:
                errors.append(doctype + "." + name + " must link to " + target)
            if df.fieldtype == "Link" and not frappe.db.exists("DocType", df.options):
                errors.append("Missing linked master: " + str(df.options))
    return errors


def validate_schema(allow_missing_invoice_link=False):
    errors = inspect_schema(allow_missing_invoice_link)
    if errors:
        frappe.throw("Meta Conversion compatibility check failed:\n" + "\n".join(errors))


def before_install():
    # setup() creates this one app-owned field; all other fields must already exist.
    validate_schema(allow_missing_invoice_link=True)


def encounter_filter_values(fieldname):
    df = frappe.get_meta("Patient Encounter").get_field(fieldname)
    if not df:
        frappe.throw("Missing Patient Encounter field: " + fieldname)
    if df.fieldtype == "Select":
        return sorted({value.strip() for value in (df.options or "").splitlines() if value.strip()})
    if df.fieldtype == "Link":
        if not df.options or not frappe.db.exists("DocType", df.options):
            frappe.throw("Missing encounter master for " + fieldname)
        master = frappe.get_meta(df.options)
        filters = {}
        if master.has_field("is_active"):
            filters["is_active"] = 1
        if master.has_field("disabled"):
            filters["disabled"] = 0
        # Link fields store document names, not display labels.
        return frappe.get_all(df.options, filters=filters, pluck="name", order_by="name", limit_page_length=0)
    frappe.throw("Encounter filter must be a Select or Link field: " + fieldname)
