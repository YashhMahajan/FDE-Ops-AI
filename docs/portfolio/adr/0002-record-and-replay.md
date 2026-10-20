# 0002: Record and Replay of Each Model Call, with Free Models Only

*Status: accepted.*

## Context

The project must not use paid model APIs. Free models have request limits for each minute and for each day. Model outputs change between calls. CI must evaluate each change of the code without model calls.

## Decision

- All providers use the OpenAI-compatible protocol: OpenRouter (free models), vLLM, Ollama or a custom URL. A change of provider is one line of configuration.
- Each model call can go through a cassette. The key is a hash of the model name and the full request. In `record` mode, the platform keeps the response. In `replay` mode, it gets the response from the cassette. A missing response is an error, not a new call.
- A rule-based stand-in model tests the pipeline. Each result from it has the label `pipeline-test`.

## Alternatives

- **A paid API with a small budget.** The author does not accept a paid API.
- **Only live calls.** Results then change at each run, and CI needs a key.

## Results

- A replay costs nothing and gives the same numbers. `fdeops regress` uses replay in CI.
- A change of the prompt changes the requests. Thus, it needs a new recording. This is correct: the previous responses are not evidence for the new prompt.
- The Kaggle notebook records large sets with vLLM on a free GPU.
