"""Generate the app's standard Frappe DocType definitions."""
import json
from pathlib import Path

root = Path(__file__).parent / "meta_conversion" / "meta_conversion"
root.mkdir(exist_ok=True)
(root / "__init__.py").touch()
(root / "doctype").mkdir(exist_ok=True)
(root / "doctype" / "__init__.py").touch()


def field(name, kind, options=None, **kw):
    return dict(fieldname=name, label=name.replace("_", " ").title(), fieldtype=kind, **({"options": options} if options else {}), **kw)


def doctype(name, fields, child=False, single=False, code=None):
    slug = name.lower().replace(" ", "_")
    folder = root / "doctype" / slug
    folder.mkdir(exist_ok=True)
    (folder / "__init__.py").touch()
    data = dict(doctype="DocType", name=name, module="Meta Conversion", engine="InnoDB", istable=int(child), issingle=int(single), field_order=[f["fieldname"] for f in fields], fields=fields, permissions=[] if child else [dict(role="System Manager", read=1, write=1 if single else 0, create=1 if name in ("Meta Encounter Type", "Meta Encounter Place") else 0, report=1, export=1)], track_changes=1)
    if not child and not single:
        data["autoname"] = "field:label" if name in ("Meta Encounter Type", "Meta Encounter Place") else "hash"
    (folder / (slug + ".json")).write_text(json.dumps(data, indent=2) + "\n")
    (folder / (slug + ".py")).write_text(code or f"from frappe.model.document import Document\n\n\nclass {name.replace(' ', '')}(Document):\n    pass\n")


for name in ["Meta Encounter Type", "Meta Encounter Place"]:
    doctype(name, [field("label", "Data", reqd=1, unique=1)])
for name, target in [("Meta Conversion Type Filter", "Meta Encounter Type"), ("Meta Conversion Place Filter", "Meta Encounter Place"), ("Meta Conversion Sales Filter", "SR Sales Type")]:
    doctype(name, [field("value", "Link", target, reqd=1, in_list_view=1)], child=True)

doctype("Meta Conversion Settings", [
    field("enabled", "Check"), field("trigger_status", "Select", "Paid", default="Paid", reqd=1),
    field("go_live", "Datetime", reqd=1, description="Only invoices created on or after this cutoff qualify. Set before enabling; historical invoices are excluded."),
    field("encounter_types", "Table MultiSelect", "Meta Conversion Type Filter"),
    field("sales_types", "Table MultiSelect", "Meta Conversion Sales Filter"),
    field("encounter_places", "Table MultiSelect", "Meta Conversion Place Filter"),
    field("provider_url", "Data", description="HTTPS Haptik base URL, without the conversions endpoint path."),
    field("api_token", "Password"), field("test_mode", "Check", default="1", description="Local eligibility check only. No request is sent."),
], single=True, code='''from urllib.parse import urlparse
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
''')
doctype("Meta Conversion Event", [
    field("sales_invoice", "Link", "Sales Invoice", reqd=1, unique=1, in_list_view=1),
    field("encounter", "Link", "Patient Encounter"), field("crm_lead", "Link", "CRM Lead"),
    field("status", "Select", "Pending\nSending\nProvider Accepted\nFailed\nUnknown\nSkipped\nTested", in_list_view=1),
    field("amount", "Currency", "INR"), field("qualified_at", "Datetime", description="Time first observed eligible; scheduled detection may lag the Paid transition."),
    field("test_mode", "Check"), field("detail", "Small Text"),
])
folder = root / "doctype" / "meta_conversion_event"
(folder / "meta_conversion_event.js").write_text('''frappe.ui.form.on("Meta Conversion Event", {
    refresh(frm) {
        if (!frm.is_new() && ["Skipped", "Tested", "Failed"].includes(frm.doc.status) && frappe.user.has_role("System Manager")) {
            frm.add_custom_button(__("Re-evaluate"), () => frappe.call({
                method: "meta_conversion.api.reevaluate",
                args: {event_name: frm.doc.name}, freeze: true,
                callback: () => frm.reload_doc()
            }));
        }
    }
});
''')
