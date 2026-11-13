# Moldova Settlements

An ERPNext v15 app that takes a Moldova payment-system register and carries it through to the books that already exist.

A customer pays through NovaPay, MegaMega, or a MAIB card. The payment system sends a file: who paid how much, how much it kept as a fee, and how much it transferred to the bank. The money arrives as one lump sum, not as a separate receipt for each customer. Without this app, an accountant matches the file, the statement, and the payments in ERPNext by hand.

The app reads the file into one Settlement Register, groups the rows by the day the money left for the bank, and shows what already agrees with the books and what is still open. It does not invent the three amounts. It stores the payment, the fee, and the net exactly as the file calculated them.

Field lists, formulas, and the sample files are in [docs/plan.md](docs/plan.md). This page is the order of work and the cases an accountant actually meets.

## The four sources

| Source | What the bank receives | Where the fee goes |
| --- | --- | --- |
| NovaPay | The payment minus the fee | The supplier’s commission Purchase Invoice |
| MegaMega | The payment minus the fee | The supplier’s commission Purchase Invoice |
| MAIB Ecomm | The payment minus the fee | A fee journal entry posted by the register |
| MAIB POS | The full payment, then a separate fee debit | The bank reconciliation of that debit |

**NovaPay and MegaMega.** The customer paid 100. The system kept 3. The bank received 97.

The customer payment is 100, into a clearing account used only for these receipts. The fee of 3 is not posted again as an expense: the supplier already billed it on a Purchase Invoice. The bank receipt of 97 is reconciled from that clearing account to the bank. Then 100 equals 97 plus 3.

**MAIB Ecomm.** The same 100, 3, and 97. The register itself posts the fee: debit the fee account 3, credit the clearing account 3. The customer payment is again 100 into clearing, and the bank receipt is 97.

**MAIB POS.** The bank deposits the full 100 and later withdraws the fee, often as separate lines by card type. The register does not post its own fee journal entry. Reconciling those withdrawals already does. A till sale is usually already paid on the invoice, so the app does not create a second customer payment. The bank deposit moves the 100 from clearing to the bank.

## One register, from the file to Reconciled

**The file becomes a draft.** An email or an upload creates the document. The document name is a series such as `STR-2026-00012`. The number printed on the form is the number from the file: a NovaPay register number, a MAIB period and terminal, or, for MegaMega, the dates and the amount, because that file has no number of its own.

Loading the same number again does nothing while a draft or a submitted register with that number still exists. After that register is cancelled, the file can be loaded again and becomes a new document.

Accounts, the mode of payment, and the bank account are copied from Settlements Settings for this company and this source. They can still be changed on the draft.

Each file row becomes a payment row. Rows that share a transfer date are gathered into one fee row and one deposit row. A NovaPay file is usually one date, so the register has one fee and one deposit. A monthly MAIB POS file has many dates, and each date gets its own pair. Several sales on one transfer date stay one group: the bank sent them together.

**A draft only links documents that already exist.** Identify, from the Actions menu, looks for a payment, a POS invoice, a bank receipt, a fee withdrawal, or a commission invoice, and writes the link into an empty row. It never replaces a link that was set by hand. A draft does not create journal entries or new payments. Submitting the register does not run these searches.

**Submit means the supplier’s report is accepted.** It does not wait until every customer and every bank row has been found. After submit the register is Unreconciled until the cases below are closed. Payment rows cannot be added or removed after submit. The customer on a row can still be changed until a payment or a sales invoice is linked.

**The register becomes Reconciled on its own** when every part is closed:

- every payment row has a Payment Entry or a Sales Invoice;
- every deposit’s Bank Transaction has status Reconciled;
- for MAIB POS, the fee withdrawals for that date add up to the fee, and each of them is reconciled;
- for MAIB Ecomm, each fee row has its fee journal entry;
- for NovaPay and MegaMega, each fee row has the journal entry that paid its share of the commission invoice.

One empty customer row keeps the whole register Unreconciled.

The dot on a row is the same check, seen earlier. Green means the row is closed. Yellow means the missing document can still be created or posted. Red means the row does not have enough to go on: no customer, no account, or no amount.

## Cases

**The payment is already in ERPNext.** Identify Payment Documents finds one submitted Receive payment for the same company, amount, clearing account, and mode of payment. If the row already has a customer, the payment must be that customer. One match is written on the row. Two matches leave the row empty, and a person chooses. A payment already used on another open register is not offered again.

**The till already took the card payment.** For MAIB POS the search does not look for a Payment Entry. It looks for one submitted POS Sales Invoice whose transaction reference equals the row’s reference, paid with this mode of payment for this amount. If the Sales Invoice has no reference field, the search does nothing. NovaPay, MegaMega, and MAIB Ecomm look for Payment Entries, not for POS invoices.

**Nothing was found, and the source is allowed to create a payment.** Create Missing Payments is a separate button, and only after submit. It posts a Receive payment for the row amount, the row’s customer, the clearing account, and the mode of payment. A reversal row is skipped. A row that already has a payment or a sales invoice is skipped. The customer can come from the row or from the default customer in settings. Until a payment is linked, that customer can still be changed. Once a customer is chosen, search and the link list stay on that customer.

**The bank receipt is the net payout.** Identify Deposit Bank Transactions looks on the source’s bank account, on the transfer date, for one submitted Bank Transaction whose deposit equals the row, whose description contains the source’s text, and whose party is the source’s supplier. NovaPay looks for “PLATA PENTRU RAMBURS”, MegaMega for “Conform contractul”, MAIB POS for “Transfer pentru operatiuni de acceptare a cardurilor”, and MAIB Ecomm for “la plata Ecomm”. A non-ecomm source ignores a description that also says “ecomm”, so a card payout is not taken for an internet payout. One match is linked. The register copies the payment or journal entry already reconciled on that bank transaction. It does not create that voucher.

**MAIB POS fee withdrawals.** Identify Fee Bank Transactions looks for withdrawals on the same day, from the same supplier, whose description contains “Comision acceptare carduri”. They are linked only when the withdrawals that are still free, together with any already linked, add up exactly to that date’s fee. A day whose withdrawals are 1.20 and 0.80 against a fee of 2.00 is linked. A day that is short, or over, is left alone.

**NovaPay or MegaMega commission invoice, still short.** October’s invoice is 200. This register’s fee is 3, and the other submitted registers linked to the same invoice add up to 150. Submit links nothing by itself. Identify Commission Invoices fills the fee row when there is exactly one submitted Purchase Invoice from that source’s supplier, in the register currency, whose eFactura delivery date is in the same month as the fee, and which still has room for the fee. The row can also be filled by hand. Submit then does not pay the invoice. The fee row stays without a journal entry, and the register cannot become Reconciled on the fee until the invoice is paid from the registers.

**The same invoice is now covered.** A later register brings the linked fees to 200, which is the invoice total, and the invoice still has at least that unpaid amount outstanding. Submit of that register, or a save of an already submitted register that closes the gap, pays the invoice. Each unpaid fee row gets its own journal entry, dated with the invoice: debit the supplier against the Purchase Invoice, credit the clearing account, for that row’s fee. An older fee journal entry that this register posted as an expense, before commission invoices were used, is cancelled and replaced by this payment. The other registers that share the invoice are updated with their own journal entries.

A fee dated outside the invoice’s eFactura month is rejected. Fees allocated to one invoice cannot exceed its total. The invoice must be submitted, for this company, this currency, and this source’s supplier.

**MAIB Ecomm fee on submit.** Submit posts one journal entry per fee row that has an amount and does not already have a journal entry: debit the fee account, credit the clearing account, on the fee date. The clearing account and the fee account are required. A day that also appears on another MAIB Ecomm register, but does not match it payment by payment, is not posted. The form says that this day differs from the other register.

**The same MAIB Ecomm day arrives twice.** A daily file and a monthly file can both contain 9 September, the same references, and the same amounts. The second register copies the payment, the fee journal entry, and the bank transaction from the first. It does not post a second fee and does not create a second payment. The first register cannot be cancelled while the second still uses a journal entry that the first created. Cancel the copy first.

**Cancel.** Cancel cancels only the Payment Entries and Journal Entries this register created. A payment or a journal entry that was found, or copied from another register, is left submitted and the link is cleared. A Sales Invoice, a Purchase Invoice, and a Bank Transaction are not cancelled. After cancel, the same file can be imported again.

**The monthly MAIB settled report.** That file is refused. Its month is the transfer dates, so it includes payments authorized at the end of the previous month and leaves out payments authorized on the last day of this month. A MAIB report that covers more than one day is loaded only from the authorization file. `ComisAuth` in that file makes the register MAIB Ecomm. Without it, the register is MAIB POS. A daily settled report is still loaded: it is one transfer day and matches the amount that arrived that morning.

**A reversal row.** A non-zero MAIB reversal (`SumaReversa`, a cash reversal, or a returned fee) gets no payment. It stays red, and the register cannot become Reconciled. How to post it will be decided from the first live file that contains one.

## What is set once

Settlements Settings has one row per company and source. The row holds the clearing account, the fee account, the bank account, the supplier, the text required in the payout description, the mode of payment, and the default customer. Searching for payments that already exist, and creating a payment when nothing was found, are separate switches. For cards, creation stays off until the invoice carries the transaction reference: amount and time cannot tell a new payment from a sale that was already rung up.

The fee account is used by MAIB Ecomm. NovaPay and MegaMega pay the commission Purchase Invoice instead. MAIB POS does not post a fee journal entry at all.

The supplier is the party on the payout, and on MAIB POS fee withdrawals. For NovaPay and MegaMega it is also the supplier of the commission Purchase Invoice.

Form labels are English. The screen is translated into Russian and Romanian.

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app erpnext_moldova_settlements
```

Mail and the banking module are optional. ERPNext and the file are enough to create a draft. Bank matching needs Bank Transactions. Commission invoices for NovaPay and MegaMega need a Purchase Invoice linked to an eFactura.

For development, [pre-commit](https://pre-commit.com/#installation) is installed in the app directory: ruff, eslint, prettier, pyupgrade. Tests run on a separate test site.

License: MIT.
