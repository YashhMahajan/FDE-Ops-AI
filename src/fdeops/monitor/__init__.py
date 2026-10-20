"""Production monitoring with signals that a live deployment can see.

The evaluation engine compares each trial with the oracle. Production traffic has no oracle. Thus,
the monitor uses only signals that a deployment can see at run time: escalations, tool errors,
guardrail flags, superseded knowledge in the context, latency and tokens. In the simulation, the
platform also knows the oracle result. Thus, it can measure how many real failures the monitor sees,
and how many failures are silent.
"""
