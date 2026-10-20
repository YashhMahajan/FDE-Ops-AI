# Real Model Runs

*Language: ASD-STE100. Refer to the [glossary](../glossary.md).*

The tests and the demo use a rule-based stand-in model. Its results have the label `pipeline-test`. They show that the platform operates. They do not measure an agent. This guide tells how to record runs with a real model, at no cost.

## How record and replay operate

Each model call goes through a cassette. In `record` mode, the platform sends the call to the model and keeps the request and the response. In `replay` mode, the platform gets the response from the cassette. Replay needs no key, no GPU and no network. Thus, CI can replay each recorded run on each change.

The cassette key includes the model name and the full request. If you change the prompt, the requests change. Then you must record again.

## Alternative 1: OpenRouter free models

OpenRouter has free models (their IDs end in `:free`). Free models have a request limit for each minute and for each day. Thus, use this alternative for a small regression set.

1. Make a key at OpenRouter. Do not put the key in a file in the repository.
2. Select a free model that supports tool calls.
3. Set the key in your shell, and run the script:

```bash
export OPENROUTER_API_KEY=your-key
MODEL=org/model-name:free scripts/record_openrouter.sh
```

4. Replay the recording without the key:

```bash
uv run fdeops regress evals/regression.yaml  # needs a recording
```

5. Set `min_success_lower` in `evals/regression.yaml` to the recorded lower limit, minus a small margin.
6. Commit `evals/regression.yaml` and the files in `evals/cassettes/`.

The script records 12 dev cases for each tenant. Change the number with `LIMIT=20`. The client waits and tries again after an HTTP 429 response.

## Alternative 2: vLLM on a free Kaggle GPU

Kaggle gives free GPU hours each week. The notebook `kaggle/fdeops_vllm_recording.ipynb` serves an open model with vLLM. The default model is Qwen2.5-7B-Instruct (AWQ). It supports tool calls with the `hermes` parser. Use this alternative for the benchmark and for the demo with a real model.

1. Make a new Kaggle notebook, and import the file `kaggle/fdeops_vllm_recording.ipynb`.
2. Set the accelerator to a GPU, and set the internet to on.
3. The repository is private. Add a Kaggle secret `GITHUB_TOKEN` with read access to this repository only.
4. Run all cells. The notebook records three sets:
   - the regression set (dev split),
   - the benchmark (test split, three trials for each case),
   - the flagship demo for each tenant, with the export for the web UI.
5. Download `fdeops-recordings.zip`, and put its files in your local copy of the repository.
6. Replay the regression set, then commit the cassettes, the runs and the reports.

## What changes with a real model

- The provenance label changes from `pipeline-test` to `measured-in-simulation`.
- The release gates can fail. That is correct. A gate that fails is a result, not an error.
- The diagnosis can find classes that the stand-in model does not show, for example `grounding_failure` or `bad_arguments`.
- The production monitor can find silent failures. These are failures without a flag. The report gives a review sample for them.
