class InvalidSmilesError(ValueError):
    """SMILES string is unparseable, or has no C=C vinyl double bond."""


class PipelineStepError(RuntimeError):
    """A pipeline step (obabel/ORCA/Multiwfn) failed. Carries which step and why."""

    def __init__(self, step: str, message: str, log_tail: str = ""):
        self.step = step
        self.log_tail = log_tail
        super().__init__(f"[{step}] {message}")
