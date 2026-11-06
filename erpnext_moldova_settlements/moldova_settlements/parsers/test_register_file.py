# Copyright (c) 2026, Evgheni Nemerenco and contributors
# For license information, please see license.txt

import unittest
from decimal import Decimal
from pathlib import Path

from erpnext_moldova_settlements.moldova_settlements.parsers.register_file import (
	AutorizatReport,
	parse_register_file,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _parse(folder, filename):
	path = EXAMPLES / folder / filename
	return parse_register_file(str(path), path.name)


class TestRegisterFile(unittest.TestCase):
	def test_novapay_amounts_come_from_the_file(self):
		parsed = _parse("novapay", "Реестр платежей №00000008204.XLSX")
		self.assertEqual(parsed["source"], "NovaPay")
		self.assertEqual(parsed["register_number"], "NP-00000008204")
		self.assertEqual(len(parsed["payments"]), 1)
		row = parsed["payments"][0]
		self.assertEqual(row["external_number"], "SHMD9407985769")
		self.assertEqual(row["payment_amount"], Decimal("2213.00"))
		self.assertEqual(row["fee_amount"], Decimal("55.33"))
		self.assertEqual(row["net_amount"], Decimal("2157.67"))
		self.assertEqual(row["transfer_date"], "2026-06-15")

	def test_novapay_file_with_two_rows_keeps_both(self):
		parsed = _parse("novapay", "Реестр платежей №00000015659.XLSX")
		self.assertEqual(len(parsed["payments"]), 2)
		self.assertEqual(
			[row["external_number"] for row in parsed["payments"]],
			["SHMD4955737516", "SHMD9624903944"],
		)

	def test_megamega_rounds_float_noise_without_recalculating(self):
		parsed = _parse("megamega", "Реестр платежей.XLSX")
		row = parsed["payments"][0]
		self.assertEqual(parsed["register_number"], "MM-2026-07-06-688.00-2026-06-17")
		self.assertEqual(row["payment_amount"], Decimal("688.00"))
		self.assertEqual(row["fee_amount"], Decimal("127.97"))
		self.assertEqual(row["net_amount"], Decimal("560.03"))
		self.assertEqual(row["payment_amount"], row["fee_amount"] + row["net_amount"])

	def test_maib_pos_decontat_totals_and_transfer_dates(self):
		parsed = _parse("maib pos", "aDetailPayRep_lunar_decontat20261002_HOTEL LIFE SRL SmartPOS.xlsx")
		self.assertEqual(parsed["source"], "MAIB POS")
		self.assertEqual(parsed["register_number"], "MAIB-S0101949-2026-09-01-2026-09-30")
		self.assertEqual(parsed["currency"], "MDL")
		self.assertEqual(len(parsed["payments"]), 89)
		self.assertEqual(len({row["transfer_date"] for row in parsed["payments"]}), 27)
		self.assertEqual(sum(row["payment_amount"] for row in parsed["payments"]), Decimal("105767.70"))
		self.assertEqual(sum(row["fee_amount"] for row in parsed["payments"]), Decimal("1422.31"))
		self.assertEqual(sum(row["net_amount"] for row in parsed["payments"]), Decimal("104345.39"))

	def test_maib_autorizat_is_rejected(self):
		path = EXAMPLES / "maib pos" / "aDetailPayRep_lunar_autorizat20261002_HOTEL LIFE SRL SmartPOS.xlsx"
		with self.assertRaises(AutorizatReport):
			parse_register_file(str(path), path.name)

	def test_maib_ecomm_fee_includes_authorization_commission(self):
		parsed = _parse("maib pos", "aDetailPayEcommRep_decontat20260909_Ecomm HOTEL LIFE S.R.L.xlsx")
		self.assertEqual(parsed["source"], "MAIB Ecomm")
		self.assertEqual(parsed["register_number"], "MAIB-E0103299-2026-09-09-2026-09-09")
		row = parsed["payments"][0]
		self.assertEqual(row["external_number"], "625107054986")
		self.assertEqual(row["payment_amount"], Decimal("1940.00"))
		self.assertEqual(row["fee_amount"], Decimal("59.20"))
		self.assertEqual(row["net_amount"], Decimal("1880.80"))
