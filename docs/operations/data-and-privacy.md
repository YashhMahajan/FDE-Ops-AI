# Data and Privacy

*Language: ASD-STE100. Refer to the [glossary](../glossary.md).*

## Data in this repository

All companies, persons, tickets and records in this repository are fictional. Each tenant file has `fictional: true`, and the loader stops if it is missing. Do not add real customer data.

## Data that the service keeps

| data | where | contains personal data |
|---|---|---|
| Run records and traces | the artifact folder | Yes, if tickets have names, emails or addresses. Turn on PII redaction. |
| Trial summaries, annotations | the database | No, except the name of the annotator |
| The audit log | the database | The name of the actor of each event |
| API keys | the database | No. Only the hash of each key. |

## PII redaction

Each tenant can turn on redaction in `tenant.yaml` (`pii.redact: true`). The service removes emails, card numbers, phone numbers and the patterns of the tenant (for example addresses) from the stored traces. The redaction occurs after the scores, thus the scores use the real text.

## Model providers

A model call sends the ticket and the knowledge base text to the provider.

- **Free OpenRouter models.** Some providers of free models can keep prompts or use them for training. Use them only with fictional data.
- **Real customer data.** Use a self-hosted model (vLLM) in the infrastructure of the customer, or a provider with a data processing agreement. Turn on PII redaction.

## Retention and deletion

- The service does not delete data automatically. The operator sets the retention for each customer contract.
- To delete all data of a tenant, use `fdeops db purge-tenant`. Refer to the [runbook](runbook.md).
- Backups keep deleted data until the backups expire (30 days in the runbook).
