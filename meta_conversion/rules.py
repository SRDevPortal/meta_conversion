def eligible(invoice, encounter, selections):
    if invoice.get("docstatus") != 1 or invoice.get("status") != "Paid" or invoice.get("is_return"):
        return "Invoice is not a submitted Paid sale"
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
