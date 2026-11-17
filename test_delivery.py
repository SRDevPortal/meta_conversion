"""Isolated orchestration tests: no database, network, or credentials."""
import importlib
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch


class Doc(dict):
    def __getattr__(self, key):
        return self.get(key)
    def __setattr__(self, key, value):
        self[key] = value
    def as_dict(self):
        return dict(self)


fake = types.ModuleType("frappe")
fake.whitelist = lambda: lambda fn: fn
fake.throw = lambda message: (_ for _ in ()).throw(ValueError(message))
fake.db = MagicMock()
fake.get_doc = MagicMock()
fake.get_all = MagicMock()
fake.get_single = MagicMock()
fake.enqueue = MagicMock()
utils = types.ModuleType("frappe.utils")
utils.get_datetime = lambda value: value
utils.now_datetime = lambda: datetime(2026, 11, 17)
fake.utils = utils
with patch.dict(sys.modules, {"frappe": fake, "frappe.utils": utils}):
    api = importlib.import_module("meta_conversion.api")
    provider = importlib.import_module("meta_conversion.provider")


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        for name in ("db", "get_doc", "get_all", "get_single", "enqueue"):
            setattr(fake, name, MagicMock())
        self.settings = Doc(enabled=1, go_live=datetime(2026, 1, 1), channel_account="WA-A",
                            test_mode=1, allowed_invoice_statuses=[Doc(value="Unpaid")],
                            encounter_types=[Doc(value="Order")], sales_types=[Doc(value="New")],
                            encounter_places=[Doc(value="Online")])
        self.invoice = Doc(name="INV", docstatus=1, status="Unpaid", currency="INR",
                           grand_total=1000, creation=datetime(2026, 2, 1), source_encounter="ENC")
        self.encounter = Doc(name="ENC", sr_source_crm_lead="LEAD", sr_encounter_type="Order",
                             sr_sales_type="New", sr_encounter_place="Online")
        self.lead = Doc(name="LEAD", sr_w_ctwa_clid="click", sr_w_source_id="ad")
        fake.get_single.return_value = self.settings
        fake.get_doc.side_effect = lambda dt, name: {
            "Sales Invoice": self.invoice, "Patient Encounter": self.encounter, "CRM Lead": self.lead
        }[dt]
        fake.get_all.return_value = [Doc(name="CHAT", channel_account="WA-A")]

    def test_matching_conversation(self):
        self.assertEqual(api.context("INV", self.settings)[3], "")
        self.assertEqual(fake.get_all.call_args.kwargs["filters"]["ctwa_clid"], "click")

    def test_wrong_or_ambiguous_account(self):
        for rows in ([], [Doc(name="CHAT", channel_account="WA-B")],
                     [Doc(name="A", channel_account="WA-A"), Doc(name="B", channel_account="WA-B")]):
            fake.get_all.return_value = rows
            self.assertTrue(api.context("INV", self.settings)[3])

    def test_snapshot_survives_lead_attribution_change(self):
        snapshot = {"channel_account": "WA-A", "encounter": "ENC", "crm_lead": "LEAD", "ad_id": "original-ad", "ctwa_clid": "original-click"}
        _, _, lead, reason = api.context("INV", self.settings, snapshot)
        self.assertEqual(reason, "")
        self.assertEqual(lead.sr_w_source_id, "original-ad")
        fake.get_all.assert_not_called()

    def test_encounter_attribution_preferred(self):
        self.encounter.sr_w_ctwa_clid = "encounter-click"
        self.encounter.sr_w_source_id = "encounter-ad"
        self.assertEqual(api.context("INV", self.settings)[3], "")
        self.assertEqual(fake.get_all.call_args.kwargs["filters"]["ctwa_clid"], "encounter-click")

    def test_changed_source_links_block_snapshot(self):
        self.assertTrue(api.context("INV", self.settings, {
            "channel_account": "WA-A", "encounter": "OTHER", "crm_lead": "LEAD",
            "ad_id": "ad", "ctwa_clid": "click"
        })[3])

    def test_account_change_blocks_snapshot(self):
        self.assertTrue(api.context("INV", self.settings, {
            "channel_account": "WA-B", "encounter": "ENC", "crm_lead": "LEAD", "ad_id": "ad", "ctwa_clid": "click"
        })[3])

    def test_accepted_purchase_is_not_requeued(self):
        fake.db.get_value.return_value = Doc(name="EVENT", status="Provider Accepted")
        api.evaluate("INV")
        fake.enqueue.assert_not_called()
        fake.get_doc.assert_not_called()

    def test_scan_uses_selected_statuses(self):
        fake.get_all.side_effect = [[], []]
        api.scan()
        self.assertEqual(fake.get_all.call_args_list[0].kwargs["filters"]["status"], ["in", ["Unpaid"]])

    def test_local_test_never_sends(self):
        event = Doc(status="Pending", sales_invoice="INV", test_mode=1,
                    attribution_snapshot='{"channel_account":"WA-A","ad_id":"ad","ctwa_clid":"click"}')
        event.save = MagicMock()
        fake.get_doc.side_effect = None
        fake.get_doc.return_value = event
        with patch.object(api, "context", return_value=(self.invoice, self.encounter, self.lead, "")), patch.object(api.requests, "post") as post:
            api.deliver("EVENT")
        post.assert_not_called()
        self.assertEqual(event.status, "Tested")

    def test_unconfirmed_contract_never_sends(self):
        self.settings.test_mode = 0
        event = Doc(status="Pending", sales_invoice="INV", test_mode=0,
                    attribution_snapshot='{"channel_account":"WA-A","ad_id":"ad","ctwa_clid":"click"}')
        event.save = MagicMock()
        fake.get_doc.side_effect = None
        fake.get_doc.return_value = event
        with patch.object(api, "context", return_value=(self.invoice, self.encounter, self.lead, "")), patch.object(api.requests, "post") as post:
            api.deliver("EVENT")
        post.assert_not_called()
        self.assertEqual(event.status, "Failed")

    def test_only_approved_origin(self):
        self.assertEqual(provider.validate_origin("https://api.interakt.ai/"), "https://api.interakt.ai")
        for url in ("http://api.interakt.ai", "https://evil.example", "https://api.interakt.ai.evil.example",
                    "https://key@api.interakt.ai", "https://api.interakt.ai/path", "https://api.interakt.ai?x=1"):
            with self.assertRaises(ValueError):
                provider.validate_origin(url)

    def test_account_key_is_read_from_chat_account(self):
        account = Doc(channel_type="Interakt", is_active=1)
        account.get_password = MagicMock(return_value="test-key")
        fake.get_doc.side_effect = None
        fake.get_doc.return_value = account
        self.assertIs(provider.get_account(self.settings, require_key=True), account)
        account.get_password.assert_called_once_with("interakt_api_key", raise_exception=False)


if __name__ == "__main__":
    unittest.main()
