"""Credential access is restricted to the approved Interakt origin."""
from urllib.parse import urlsplit

import frappe


def validate_origin(value):
    url = urlsplit(value or "")
    if (url.scheme != "https" or url.netloc != "api.interakt.ai"
            or url.path not in ("", "/") or url.query or url.fragment):
        frappe.throw("Provider URL must be https://api.interakt.ai.")
    return "https://api.interakt.ai"


def get_account(settings, require_key=False):
    if not settings.get("channel_account"):
        frappe.throw("Select an Interakt Chat Channel Account.")
    account = frappe.get_doc("Chat Channel Account", settings.channel_account)
    if account.channel_type != "Interakt" or not account.is_active:
        frappe.throw("Select an active Interakt Chat Channel Account.")
    if require_key and not account.get_password("interakt_api_key", raise_exception=False):
        frappe.throw("The selected Chat Channel Account has no Interakt API key.")
    return account
