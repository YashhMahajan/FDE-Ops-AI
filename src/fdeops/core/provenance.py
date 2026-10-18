from enum import StrEnum


class Provenance(StrEnum):
    """Where a number came from. Every report carries one; nothing is presented without it."""

    MEASURED_IN_SIMULATION = "measured-in-simulation"
    ESTIMATED = "estimated"
    PIPELINE_TEST = "pipeline-test"
