import importlib
import sys
import types
import unittest
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

fake = types.ModuleType("frappe")
with patch.dict(sys.modules, {"frappe": fake}):
    compatibility = importlib.import_module("meta_conversion.compatibility")


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.frappe = MagicMock()
        self.frappe.throw.side_effect = ValueError
        self.frappe.db.exists.return_value = True
        self.fields = {}
        for dt, fields in compatibility.REQUIRED_FIELDS.items():
            self.fields[dt] = {}
            for name, (kinds, target) in fields.items():
                kind = kinds if isinstance(kinds, str) else kinds[0]
                self.fields[dt][name] = NS(fieldtype=kind, options=target or "")
        self.frappe.get_meta.side_effect = lambda dt: NS(
            get_field=lambda name: self.fields.get(dt, {}).get(name),
            has_field=lambda name: name in self.fields.get(dt, {}),
        )
        self.patch = patch.object(compatibility, "frappe", self.frappe)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_select_clinic_schema(self):
        self.assertEqual(compatibility.inspect_schema(), [])

    def test_link_clinic_schema(self):
        for field, target in (("sr_encounter_type", "SR Encounter Type"),
                              ("sr_encounter_place", "SR Encounter Place")):
            self.fields["Patient Encounter"][field] = NS(fieldtype="Link", options=target)
        self.assertEqual(compatibility.inspect_schema(), [])

    def test_only_invoice_link_can_be_created_by_install(self):
        del self.fields["Sales Invoice"]["source_encounter"]
        self.assertEqual(compatibility.inspect_schema(True), [])
        self.assertTrue(compatibility.inspect_schema())
        del self.fields["Patient Encounter"]["sr_source_crm_lead"]
        self.assertTrue(compatibility.inspect_schema(True))

    def test_incorrect_link_target_rejected(self):
        self.fields["Sales Invoice"]["source_encounter"].options = "Patient"
        self.assertTrue(any("must link to Patient Encounter" in e for e in compatibility.inspect_schema(True)))

    def test_missing_doctype_reports_actionable_error(self):
        self.frappe.db.exists.side_effect = lambda dt, name: name != "Chat Conversation"
        self.assertIn("Missing DocType: Chat Conversation", compatibility.inspect_schema())

    def test_missing_linked_master(self):
        self.frappe.db.exists.side_effect = lambda dt, name: name != "SR Sales Type"
        self.assertIn("Missing linked master: SR Sales Type", compatibility.inspect_schema())

    def test_select_values_normalized(self):
        self.fields["Patient Encounter"]["sr_encounter_type"].options = "\nOrder\n Appointment \nOrder\n"
        self.assertEqual(compatibility.encounter_filter_values("sr_encounter_type"), ["Appointment", "Order"])
        self.frappe.get_all.assert_not_called()

    def test_link_values_use_active_master_names(self):
        self.fields["Patient Encounter"]["sr_encounter_type"] = NS(fieldtype="Link", options="SR Encounter Type")
        self.fields["SR Encounter Type"] = {"is_active": NS(), "disabled": NS()}
        self.frappe.get_all.return_value = ["Order", "Appointment"]
        self.assertEqual(compatibility.encounter_filter_values("sr_encounter_type"), ["Order", "Appointment"])
        self.frappe.get_all.assert_called_once_with(
            "SR Encounter Type", filters={"is_active": 1, "disabled": 0},
            pluck="name", order_by="name", limit_page_length=0)

    def test_link_master_without_active_flags(self):
        self.fields["Patient Encounter"]["sr_encounter_place"] = NS(fieldtype="Link", options="SR Encounter Place")
        self.frappe.get_all.return_value = ["Online", "OPD"]
        compatibility.encounter_filter_values("sr_encounter_place")
        self.assertEqual(self.frappe.get_all.call_args.kwargs["filters"], {})

    def test_unsupported_filter_type_fails(self):
        self.fields["Patient Encounter"]["sr_encounter_type"].fieldtype = "Data"
        with self.assertRaises(ValueError):
            compatibility.encounter_filter_values("sr_encounter_type")

    def test_before_install_does_not_write(self):
        compatibility.before_install()
        self.frappe.get_doc.assert_not_called()
        self.frappe.db.set_value.assert_not_called()


if __name__ == "__main__":
    unittest.main()
