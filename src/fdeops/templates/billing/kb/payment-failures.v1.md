---
doc_id: payment-failures
title: Failed Payments
version: 1
effective_from: 2026-01-01
---

## Automatic retries {#retry-schedule}

If a payment fails, we retry the charge automatically 3 times in 7 days. Your workspace stays
active during these 7 days. If all retries fail, the account status changes to past due.

## Updating your card {#update-card}

Workspace Owners and Admins can change the card in Settings > Billing > Payment method. After you
change the card, we retry the open invoice in one hour.
