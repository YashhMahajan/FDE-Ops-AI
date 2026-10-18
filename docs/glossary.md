# Glossary

This project writes its documents in ASD-STE100 Simplified Technical English (STE), issue 9.
STE lets a writer use the technical nouns and technical verbs of a subject field (rules 1.5, 1.8
and 1.12). This glossary is the list of those terms for FDE-Ops-AI. The STE checker
(`fdeops docs check`) accepts these terms. Do not use other words for the same items (rule 1.11).

## Technical nouns

| Term | Meaning in this project |
|---|---|
| agent | The AI program that does the support work. It is the system that we test. |
| annotation | A label that a person gives to a trial. |
| audit log | The record of all changes that the agent makes. Each event has the hash of the event before it. |
| baseline | The configuration that a new configuration must be better than. |
| budget | A maximum value for steps, tokens, latency or cost. |
| calibration | A comparison of judge labels with human labels. |
| case | One support ticket with its ground truth. |
| cassette | A file that keeps the model responses of a run, for replay. |
| chunk | A part of a knowledge-base section that retrieval gives to the agent. |
| configuration (config) | The settings that control the behavior of the agent. |
| connector | The code that connects the agent to an external system. |
| critical violation | A policy violation that can cause financial or security damage. |
| dataset | A versioned set of cases. |
| diagnosis | The analysis that finds the cause of a cluster of failures. |
| drift | A change in the knowledge base, the data or the model after a release. |
| embedding | A vector that shows the meaning of a text. |
| escalation | The hand-off of a ticket to a human specialist. |
| evaluator | The code that gives a score to one aspect of an episode. |
| episode | One run of the agent on one case. |
| failure | A trial that does not get the correct result. |
| fault | An error that the simulator injects on purpose. |
| fixture | The test data that a case adds to the world. |
| gate | A rule that a release candidate must obey before it can go to production. |
| ground truth | The correct result for a case. The oracle calculates it. |
| guardrail | A check that stops a task before it occurs. |
| idempotency key | A key that makes sure that a request that the client sends again occurs only one time. |
| incident | A failure in production, or a simulation of one. |
| ingest | The step that loads business data, checks each record and writes a data-quality report. |
| injection | Text that tries to change the instructions of the agent (prompt injection). |
| judge | A model that gives a score to a reply. |
| knowledge base (KB) | The help documents of a tenant. |
| latency | The time from a request to its response. |
| opportunity | A product problem with its evidence, cost and expected value. |
| oracle | The code that calculates ground truth from the policy and the world state. |
| pack | The domain code for one business domain (for example, billing). |
| policy | The business rules of a tenant. |
| preset | A named provider configuration. |
| provenance | The source of a number: measured in simulation, estimated, or pipeline test. |
| provider | A service that gives model responses. |
| regression | A decrease in quality from one version to the next. |
| release | A frozen set of model, prompt, retrieval settings, tools and dataset. |
| retrieval | The search that finds knowledge-base sections for the agent. |
| rubric | The instructions that tell a judge how to give a score. |
| scenario | A template that makes cases of one type. |
| slice | A subset of trials, for example all trials of one scenario. |
| span | One timed step in a trace. |
| tenant | One customer of the platform. |
| trace | The record of all steps in an episode. |
| trial | One episode of a case. A run can have more than one trial for each case. |
| world | The simulated data and APIs of a tenant. |

## Technical verbs

These verbs are names of software operations:

- build, cache, call, clone, commit, configure, deploy, download, embed, enforce
- escalate, evaluate, export, fail, fork, generate, hash, import, index, inject
- ingest, install, lint, load, log, match, merge, parse, pass, push, query
- raise, rank, record, refund, render, replay, retrieve, retry, return, run
- save, score, script, search, seed, store, stream, swap, sync, test, upload, validate
