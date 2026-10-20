#!/usr/bin/env bash
# Record a small regression set with a free OpenRouter model. Replays after this cost nothing.
#
#   export OPENROUTER_API_KEY=...            (from https://openrouter.ai/keys, never commit it)
#   MODEL=<provider>/<model>:free scripts/record_openrouter.sh
#
# Free models have a request limit for each minute and for each day. The default sample is
# 12 dev cases for each tenant. Each case needs about 3 to 6 model calls. The client waits and
# tries again after an HTTP 429 response.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${OPENROUTER_API_KEY:?Set OPENROUTER_API_KEY first}"
: "${MODEL:?Set MODEL to a free OpenRouter model id, for example MODEL=<org>/<model>:free}"
LIMIT="${LIMIT:-12}"

case "$MODEL" in
  *:free) ;;
  *) echo "MODEL must end in :free (this project uses free models only)" >&2; exit 1 ;;
esac

# Write the model and the sample size into the manifest. Replays use the same values.
python3 - "$MODEL" "$LIMIT" <<'PY'
import re, sys
model, limit = sys.argv[1], sys.argv[2]
path = "evals/regression.yaml"
text = open(path).read()
text = re.sub(r"(?m)^(    model: ).*$", lambda m: m.group(1) + model, text)
text = re.sub(r"(?m)^(    limit: ).*$", lambda m: m.group(1) + limit, text)
open(path, "w").write(text)
PY

uv run fdeops regress evals/regression.yaml --record
echo
echo "Recorded. Replay without a key:  uv run fdeops regress evals/regression.yaml"
echo "Then commit evals/regression.yaml and evals/cassettes/*.jsonl."
