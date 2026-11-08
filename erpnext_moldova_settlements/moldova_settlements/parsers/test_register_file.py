# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import unittest
from decimal import Decimal

from erpnext_moldova_settlements.moldova_settlements.parsers.register_file import (
	SettledMonthReport,
	_monthly_settled_name,
	_settled_month,
	parse_register_file,
)
from erpnext_moldova_settlements.moldova_settlements.parsers.sample_workbook import (
	ecomm_daily_file,
	ecomm_month_file,
	megamega_file,
	novapay_file,
	pos_month_file,
)


def _parse(path):
	return parse_register_file(str(path), path.name)


class TestRegisterFile(unittest.TestCase):
	def test_novapay_amounts_come_from_the_file(self):
		parsed = _parse(
			novapay_file(
				"10000000001",
				[{"payment": "100.00", "fee": "3.00", "net": "97.00", "external": "SHIP-1001"}],
			)
		)
		self.assertEqual(parsed["source"], "NovaPay")
		self.assertEqual(parsed["register_number"], "NP-10000000001")
		self.assertEqual(len(parsed["payments"]), 1)
		row = parsed["payments"][0]
		self.assertEqual(row["external_number"], "SHIP-1001")
		self.assertEqual(row["payment_amount"], Decimal("100.00"))
		self.assertEqual(row["fee_amount"], Decimal("3.00"))
		self.assertEqual(row["net_amount"], Decimal("97.00"))
		self.assertEqual(row["transfer_date"], "2026-06-15")

	def test_novapay_file_with_two_rows_keeps_both(self):
		parsed = _parse(
			novapay_file(
				"10000000002",
				[
					{"payment": "100.00", "fee": "3.00", "net": "97.00", "external": "SHIP-2001"},
					{"payment": "40.00", "fee": "1.00", "net": "39.00", "external": "SHIP-2002"},
				],
			)
		)
		self.assertEqual(len(parsed["payments"]), 2)
		self.assertEqual(
			[row["external_number"] for row in parsed["payments"]],
			["SHIP-2001", "SHIP-2002"],
		)

	def test_megamega_rounds_float_noise_without_recalculating(self):
		parsed = _parse(megamega_file())
		row = parsed["payments"][0]
		self.assertEqual(parsed["register_number"], "MM-2026-07-06-100.00-2026-06-17")
		self.assertEqual(row["payment_amount"], Decimal("100.00"))
		self.assertEqual(row["fee_amount"], Decimal("13.00"))
		self.assertEqual(row["net_amount"], Decimal("87.00"))
		self.assertEqual(row["payment_amount"], row["fee_amount"] + row["net_amount"])

	def test_maib_pos_autorizat_totals_and_transfer_dates(self):
		parsed = _parse(pos_month_file("aDetailPayRep_lunar_autorizat20261002_Sample SmartPOS.xlsx"))
		self.assertEqual(parsed["source"], "MAIB POS")
		self.assertEqual(parsed["register_number"], "MAIB-S1000001-2026-09-01-2026-09-30")
		self.assertEqual(parsed["posting_date"], "2026-10-02")
		self.assertEqual(parsed["currency"], "MDL")
		self.assertEqual(len(parsed["payments"]), 2)
		self.assertEqual(parsed["payments"][0]["payment_date"], "2026-09-01")
		self.assertEqual(parsed["payments"][0]["transfer_date"], "2026-09-02")
		transfer_dates = {row["transfer_date"] for row in parsed["payments"]}
		self.assertNotIn("2026-09-01", transfer_dates)
		self.assertIn("2026-10-01", transfer_dates)
		self.assertEqual(len(transfer_dates), 2)
		self.assertEqual(sum(row["payment_amount"] for row in parsed["payments"]), Decimal("140.00"))
		self.assertEqual(sum(row["fee_amount"] for row in parsed["payments"]), Decimal("2.00"))
		self.assertEqual(sum(row["net_amount"] for row in parsed["payments"]), Decimal("138.00"))

	def test_maib_without_report_date_uses_the_period_end(self):
		path = pos_month_file("lunar_autorizat_pos.xlsx")
		parsed = parse_register_file(str(path), path.name)
		self.assertEqual(parsed["posting_date"], "2026-09-30")

	def test_maib_monthly_settled_report_is_rejected(self):
		for filename in (
			"aDetailPayRep_lunar_decontat20261002_Sample SmartPOS.xlsx",
			"aDetailPayEcommRep_lunar_decontat20261002_Ecomm Sample.xlsx",
		):
			with self.assertRaises(SettledMonthReport):
				parse_register_file("unused.xlsx", filename)

	def test_ecomm_monthly_file_names(self):
		settled = "aDetailPayEcommRep_lunar_decontat20261102_Ecomm Sample.xlsx"
		authorized = "aDetailPayEcommRep_lunar_autorizat20261102_Ecomm Sample.xlsx"
		period = ("2026-10-01", "2026-10-31")
		self.assertTrue(_monthly_settled_name(settled))
		self.assertFalse(_monthly_settled_name(authorized))
		self.assertTrue(_settled_month(settled, period))
		self.assertFalse(_settled_month(authorized, period))

	def test_ecomm_month_without_autorizat_is_rejected(self):
		path = ecomm_month_file("ecomm-month.xlsx")
		with self.assertRaises(SettledMonthReport):
			parse_register_file(str(path), "aDetailPayEcommRep_decontat20261002_Ecomm.xlsx")
		with self.assertRaises(SettledMonthReport):
			parse_register_file(str(path), "ecomm-monthly.xlsx")

	def test_maib_ecomm_fee_includes_authorization_commission(self):
		parsed = _parse(ecomm_daily_file("aDetailPayEcommRep_decontat20260909_Ecomm Sample.xlsx"))
		self.assertEqual(parsed["source"], "MAIB Ecomm")
		self.assertEqual(parsed["register_number"], "MAIB-E1000001-2026-09-09-2026-09-09")
		self.assertEqual(parsed["posting_date"], "2026-09-09")
		row = parsed["payments"][0]
		self.assertEqual(row["external_number"], "RRN-SAMPLE-1")
		self.assertEqual(row["payment_date"], "2026-09-08")
		self.assertEqual(row["transaction_datetime"], "2026-09-08 10:00:00")
		self.assertEqual(row["payment_amount"], Decimal("100.00"))
		self.assertEqual(row["fee_amount"], Decimal("3.00"))
		self.assertEqual(row["net_amount"], Decimal("97.00"))
