import unittest
from meta_conversion.rules import eligible, amount


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.invoice = dict(docstatus=1, status="Paid", currency="INR", grand_total=1000, rounded_total=1000)
        self.encounter = dict(sr_encounter_type="Order", sr_sales_type="New", sr_encounter_place="Online")
        self.filters = {key: {value} for key, value in self.encounter.items()}

    def test_paid(self):
        self.assertEqual(eligible(self.invoice, self.encounter, self.filters), "")

    def test_partial_cancelled_return_currency(self):
        for patch in [dict(status="Partly Paid"), dict(docstatus=2), dict(is_return=1), dict(currency="USD"), dict(grand_total=0, rounded_total=0)]:
            self.assertTrue(eligible(self.invoice | patch, self.encounter, self.filters))

    def test_each_filter_required(self):
        for key in self.filters:
            self.assertTrue(eligible(self.invoice, self.encounter, self.filters | {key: set()}))
            self.assertTrue(eligible(self.invoice, self.encounter, self.filters | {key: {"Other"}}))

    def test_appointment(self):
        self.filters["sr_encounter_type"].add("Appointment")
        self.assertEqual(eligible(self.invoice, self.encounter | {"sr_encounter_type": "Appointment"}, self.filters), "")

    def test_configured_statuses(self):
        for status in ("Paid", "Partly Paid", "Unpaid", "Overdue"):
            invoice = self.invoice | {"status": status}
            self.assertEqual(eligible(invoice, self.encounter, self.filters, {status}), "")
            self.assertTrue(eligible(invoice, self.encounter, self.filters, set()))

    def test_unpaid_does_not_require_cod(self):
        self.assertEqual(eligible(self.invoice | {"status": "Unpaid"}, self.encounter, self.filters, {"Unpaid"}), "")

    def test_status_configuration_cannot_allow_invalid_documents(self):
        for patch in ({"docstatus": 0}, {"docstatus": 2}, {"is_return": 1},
                      {"status": "Cancelled"}, {"status": "Draft"}, {"status": "Return"}):
            invoice = self.invoice | patch
            self.assertTrue(eligible(invoice, self.encounter, self.filters, {invoice["status"]}))

    def test_partial_reports_full_value(self):
        invoice = self.invoice | {"status": "Partly Paid", "outstanding_amount": 800}
        self.assertEqual(eligible(invoice, self.encounter, self.filters, {"Partly Paid"}), "")
        self.assertEqual(amount(invoice), 1000)

    def test_rounding(self):
        self.assertEqual(amount(self.invoice | dict(grand_total=999.8)), 1000)
        self.assertEqual(amount(self.invoice | dict(grand_total=999.8, disable_rounded_total=1)), 999.8)


if __name__ == "__main__":
    unittest.main()
