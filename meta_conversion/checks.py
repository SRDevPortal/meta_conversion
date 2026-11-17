"""Read-only installation checks, callable with bench execute."""
import frappe
from meta_conversion.rules import selected_statuses, SUPPORTED_STATUSES


def verify():
    settings = frappe.get_single("Meta Conversion Settings")
    assert "meta_conversion" in frappe.get_installed_apps()
    assert selected_statuses(settings) and selected_statuses(settings) <= SUPPORTED_STATUSES
    for table in ("allowed_invoice_statuses", "encounter_types", "sales_types", "encounter_places"):
        assert settings.meta.get_field(table).fieldtype == "Table MultiSelect"
    assert frappe.get_meta("Sales Invoice").get_field("source_encounter").options == "Patient Encounter"
    assert frappe.get_meta("Meta Conversion Event").get_field("sales_invoice").unique
    assert frappe.db.exists("Scheduled Job Type", {"method": "meta_conversion.api.scan"})
    return {"installed": True, "enabled": bool(settings.enabled), "local_test_mode": bool(settings.test_mode), "allowed_invoice_statuses": sorted(selected_statuses(settings)), "default_encounter_types": [r.value for r in settings.encounter_types], "scheduler_registered": True}
