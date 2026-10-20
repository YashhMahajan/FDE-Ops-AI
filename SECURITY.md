# Security Policy

*Language: ASD-STE100. Refer to the [glossary](docs/glossary.md).*

## Supported versions

| version | security fixes |
|---|---|
| 2.x | yes |
| earlier than 2.0 | no |

## How to report a vulnerability

Do not open a public issue for a vulnerability. Use the private report function of GitHub: go to the **Security** tab of the repository, then select **Report a vulnerability**.

Give this data in the report:

1. The version or the commit.
2. The steps to see the problem again.
3. The possible effect, for example access to the data of a different tenant, or a task without the necessary role.

## What we do after a report

| step | target time |
|---|---|
| We tell you that we received the report | 3 days |
| We tell you if the problem is a vulnerability | 10 days |
| We release a fix for a high or critical vulnerability | 30 days |

We tell you before we publish an advisory. We name you in the advisory if you agree.

## Scope

These items are in scope: the API, the job worker, the tenant guard, and the API keys and roles. The connectors, the artifact store, the Docker images and the CI workflows are also in scope.

These items are not in scope: the fictional demo data, and attacks that need a correct admin key.

## How the project prevents vulnerabilities

The [threat model](docs/operations/threat-model.md) gives the assets, the threats and the controls. CI examines each change with these tools:

- a check of the full git history for secrets,
- a check of known vulnerabilities in the Python and web dependencies,
- security rules in the linter,
- a check of the dependency licenses,
- tests that isolate the data of each tenant, and tests of roles, rate limits and input limits.
