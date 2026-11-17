import frappe
from frappe.model.document import Document

from meta_conversion.provider import get_account, validate_origin
from meta_conversion.rules import SUPPORTED_STATUSES, selected_statuses


class MetaConversionSettings(Document):
    def validate(self):
        statuses = selected_statuses(self)
        if statuses - SUPPORTED_STATUSES:
            frappe.throw("Unsupported invoice status selected.")
        if self.provider_url:
            validate_origin(self.provider_url)
        if self.channel_account:
            get_account(self)
        if self.enabled:
            if not statuses:
                frappe.throw("Select at least one invoice status.")
            if not all(self.get(f) for f in ("encounter_types", "sales_types", "encounter_places")):
                frappe.throw("Select at least one encounter type, sales type, and encounter place.")
            get_account(self, require_key=not self.test_mode)
            if not self.test_mode:
                validate_origin(self.provider_url)
                if not self.provider_contract_confirmed:
                    frappe.throw("Confirm the Interakt conversion API contract before live reporting.")
