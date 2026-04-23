from dataclasses import dataclass, field


@dataclass
class LintIssue:
    path: str
    check_id: str
    severity: str  # "error" | "warning" | "info"
    message: str
    hint: str = field(default="")
