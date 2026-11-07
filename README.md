# Moldova Settlements

An ERPNext v15 app that takes Moldova payment-system registers and carries them through to the books that already exist.

A customer pays through NovaPay, MegaMega, or a MAIB card. The payment system sends a file or an email: who paid how much, how much it kept as a fee, and how much it transferred to the account. The money arrives in the bank as one or several lump sums, not as a separate receipt for each customer. Without the register, an accountant has to match the file, the statement, and the payments in ERPNext by hand.

The app takes that matching over. It reads the file, creates one Settlement Register, splits the rows by customer and by deposit date, and shows what already agrees with the books and what still does not.

Field lists, formulas, and the sample files are in [docs/plan.md](docs/plan.md). This page is why the app exists and the order in which it works.

## What it does

One file becomes one register with a stable number taken from the file. Until that register is cancelled, loading the file again does not create a second document.

The register shows three amounts that the file has already calculated and that the app does not derive one from another:

- how much the customers paid;
- how much the system kept as a fee;
- how much should arrive, or has already arrived, in the account.

The register then links those amounts to ERPNext documents: the customer payment, the POS invoice when the sale was already posted at the till, the bank transaction, and the fee journal entry. A link can be set by hand, or the app can be asked to find it. An automatic search does not replace a link that was already set by hand.

When everything is linked and the bank amounts are reconciled, the register gets the status Reconciled. While something is still missing, it stays submitted but unreconciled: the empty row is visible.

## The jobs it does

1. Accepts a register from an email or from an uploaded file. Mail and the banking module are optional: ERPNext and the file are enough.
2. Identifies the payment system and reads its columns. Today that is NovaPay, MegaMega, MAIB POS, and MAIB Ecomm. A new source is added as its own file parser.
3. Stores each customer payment and groups payments by the date the money left for the account.
4. Creates a fee row and a deposit row for that date.
5. On submit, posts the fee where it does not arrive as its own bank line.
6. Looks for payments and POS invoices that are already submitted. If a payment is still not found, it creates one when the source settings allow it.
7. Matches incoming bank receipts and, for MAIB POS cards, the separate fee debits.
8. Marks the register reconciled only when the customer rows and the bank amounts are closed.
9. On cancel, cancels only the payments and journal entries it created itself. It does not cancel a found invoice, a bank journal entry that is already reconciled, or the bank transaction itself.

## Two ways the money reaches the bank

The whole posting depends on this.

**NovaPay, MegaMega, and MAIB internet acquiring.** The system keeps the fee before the transfer. The account receives the reduced amount. For example, the customer paid 100, the fee is 3, and 97 arrived in the account.

The register makes two entries. The customer payment is for the full 100, from a dedicated clearing account used for these payments. The fee journal entry is 3: fee expense, and the same amount credited to the clearing account. The bank receipt of 97 closes the remainder. Together, 100 equals 97 plus 3 again.

**MAIB cards on a terminal.** The bank deposits the full payment amount and debits the fee later, as separate statement lines, often by card type. The register does not create its own fee journal entry: reconciling those debits already does that. A till sale is usually already paid on the invoice, so the app does not create a new payment by default. Otherwise the customer would be paid twice. The incoming bank amount moves the money from the clearing account to the bank account.

The MAIB “authorized” report is not taken into a register. The books use the “settled” report: it holds the amounts the bank has already sent.

## How one register moves

**The file lands as a draft.** An email or an upload creates the document. The document name is a series such as `STR-2026-00012`. The number from the file is shown on the form and in the list: the NovaPay register number, the MAIB period and terminal, and for MegaMega the dates and the amount, because the file has no separate number. The same number can be loaded again only after the previous register is cancelled. Accounts are filled from the settings for this company and this payment system. They can be changed on the draft.

Each file row becomes a payment row: amount, fee, amount to transfer, and service fields such as a shipment number or a transaction reference. Rows with the same deposit date are gathered into one fee and one deposit. NovaPay and MegaMega files usually have one such date. A monthly MAIB POS report has many dates, and each date gets its own pair of rows. If several sales days sit on one transfer date, that is one group: the bank sent them together.

**A draft can only link what already exists.** The app looks for a payment, a POS invoice, or a bank transaction and writes the link into an empty row. A draft does not create journal entries or new payments. Submitting the register does not run these searches by itself.

**Submit is agreement with the supplier’s report.** It does not wait until every customer and every bank row has been found.

For NovaPay, MegaMega, and MAIB Ecomm, one fee journal entry is created on that date at this moment. MAIB POS does not create a journal entry. If a fee debit is already set and the bank has already reconciled it, the link to that journal entry is simply written on the row.

After submit, the register stands as unreconciled.

**Matching continues, by hand or from the Actions menu.** Payment search links an empty row to one matching payment or to one paid POS invoice. If there are several candidates, the row stays empty: a person has to choose. Search for bank receipts, and for MAIB card fee debits, works the same way: it fills what is empty and leaves what was already chosen.

Creating a missing payment is a separate step after submit, and only when the source allows it. The payment takes the payment amount from the row, the row’s customer, and the clearing account. A default customer can be set in the settings. Until a payment is linked, that customer can be changed. Once a customer is chosen, search and the link lists are limited to that customer.

**The register becomes reconciled on its own, when every part is closed.** Every customer payment has a link. Every deposit’s bank transaction is reconciled. For MAIB cards, the fee debits also add up to that date’s fee, and each of those debits is reconciled. One empty customer row keeps the whole register unreconciled.

The same MAIB Ecomm payment can arrive twice, in a daily report and in a monthly report. The second register takes the links that were already created and does not post a second fee journal entry for the same day. The first register can be cancelled after the one that copied the link has been cancelled.

The row colour in the grid shows the same thing without opening the status: green means linked, yellow means the rest can still be created or posted, red means the data is not enough.

## What is set once

Settings for each company and each payment system hold the clearing account, the fee account, the mode of payment, and the default customer. They also hold the bank account used to look up bank rows, the supplier who sends the payout, and the text that must appear in that payout. Choosing a source fills the default text: NovaPay “PLATA PENTRU RAMBURS”, MegaMega “Conform contractul”, MAIB POS “Transfer pentru operatiuni de acceptare a cardurilor”, and MAIB Ecomm “la plata Ecomm”. A payout is linked only when the bank transaction names that supplier. Looking up payments that are already submitted, and creating a payment when nothing was found, are switched on separately. For cards, creation stays off until the invoice carries the transaction reference: amount and time cannot reliably tell a new payment from a sale that was already rung up.

Form labels are English. The screen is translated into Russian and Romanian.

## Not done yet

A non-zero MAIB reversal (`SumaReversa`, a cash reversal, a returned fee) does not appear in the samples, and there is no live file with one yet. Such a row currently gets no payment and does not let the register become reconciled. How to post it will be decided from the first register that contains one.

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app erpnext_moldova_settlements
```

For development, [pre-commit](https://pre-commit.com/#installation) is installed in the app directory: ruff, eslint, prettier, pyupgrade. Tests run on a separate test site.

License: MIT.
