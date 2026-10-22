from urllib.parse import urlparse
import frappe
from frappe.model.document import Document


class MetaConversionSettings(Document):
    def validate(self):
        if self.trigger_status != "Paid":
            frappe.throw("Only Paid invoice status is supported.")
        if self.provider_url:
            url = urlparse(self.provider_url)
            if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
                frappe.throw("Provider URL must be an HTTPS base URL without credentials, query, or fragment.")
        if self.enabled:
            if not all(self.get(f) for f in ("encounter_types", "sales_types", "encounter_places")):
                frappe.throw("Select at least one encounter type, sales type, and encounter place.")
            if not self.test_mode and (not self.provider_url or not self.get_password("api_token")):
                frappe.throw("Provider URL and token are required for live reporting.")
