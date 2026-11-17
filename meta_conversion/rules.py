SUPPORTED_STATUSES = frozenset({"Paid", "Partly Paid", "Unpaid", "Overdue"})


def selected_statuses(settings):
    return {row.value for row in (settings.get("allowed_invoice_statuses") or [])}


def eligible(invoice, encounter, selections, statuses=None):
    if invoice.get("docstatus") != 1 or invoice.get("is_return"):
        return "Invoice is not a submitted sale"
    allowed = {"Paid"} if statuses is None else set(statuses)
    if invoice.get("status") not in (allowed & SUPPORTED_STATUSES):
        return "Invoice status is not selected"
    if invoice.get("currency") != "INR":
        return "Only INR invoices are supported"
    if amount(invoice) <= 0:
        return "Invoice amount must be positive"
    for field, allowed in selections.items():
        if not allowed or encounter.get(field) not in allowed:
            return "Encounter does not match " + field
    return ""


def amount(invoice):
    return float(invoice.get("grand_total") if invoice.get("disable_rounded_total") else (invoice.get("rounded_total") or invoice.get("grand_total") or 0))
