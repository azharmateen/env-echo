"""Security audit for .env files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

from .schema import parse_env_file


class AuditSeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class AuditFinding:
    """A security audit finding."""
    severity: AuditSeverity
    variable: str
    title: str
    description: str
    recommendation: str


@dataclass
class AuditResult:
    """Result of a security audit."""
    filepath: str
    findings: List[AuditFinding] = field(default_factory=list)
    total_vars: int = 0

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == AuditSeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == AuditSeverity.HIGH)

    @property
    def score(self) -> int:
        """Security score 0-100 (100 = no issues)."""
        if self.total_vars == 0:
            return 100
        deductions = {
            AuditSeverity.CRITICAL: 25,
            AuditSeverity.HIGH: 15,
            AuditSeverity.MEDIUM: 8,
            AuditSeverity.LOW: 3,
            AuditSeverity.INFO: 0,
        }
        total_deduction = sum(deductions.get(f.severity, 0) for f in self.findings)
        return max(0, 100 - total_deduction)


# Well-known default passwords and values
KNOWN_DEFAULTS = {
    "password", "123456", "admin", "root", "test", "demo",
    "changeme", "default", "secret", "pass", "1234", "qwerty",
    "letmein", "master", "guest", "abc123", "password1",
    "12345678", "monkey", "dragon",
}

# Patterns that suggest real API keys
API_KEY_PATTERNS = [
    (re.compile(r"^sk-[a-zA-Z0-9]{20,}$"), "OpenAI API key"),
    (re.compile(r"^ghp_[a-zA-Z0-9]{36}$"), "GitHub personal access token"),
    (re.compile(r"^gho_[a-zA-Z0-9]{36}$"), "GitHub OAuth token"),
    (re.compile(r"^github_pat_[a-zA-Z0-9_]{22,}$"), "GitHub fine-grained PAT"),
    (re.compile(r"^glpat-[a-zA-Z0-9\-_]{20,}$"), "GitLab PAT"),
    (re.compile(r"^xox[bprs]-[a-zA-Z0-9\-]+$"), "Slack token"),
    (re.compile(r"^AKIA[0-9A-Z]{16}$"), "AWS access key ID"),
    (re.compile(r"^SG\.[a-zA-Z0-9_\-]{22}\.[a-zA-Z0-9_\-]{43}$"), "SendGrid API key"),
    (re.compile(r"^sk_live_[a-zA-Z0-9]{24,}$"), "Stripe live secret key"),
    (re.compile(r"^rk_live_[a-zA-Z0-9]{24,}$"), "Stripe live restricted key"),
]


def audit(env_path: str) -> AuditResult:
    """Perform a security audit on a .env file.

    Checks:
    - Weak/default passwords
    - Known default values in production-looking configs
    - Exposed real API keys (pattern matching)
    - Empty secret variables
    - Debug mode enabled
    - Insecure URLs (http:// for sensitive endpoints)
    - Overly permissive CORS
    """
    try:
        env_vars = parse_env_file(env_path)
    except FileNotFoundError:
        return AuditResult(filepath=env_path, findings=[
            AuditFinding(
                severity=AuditSeverity.CRITICAL,
                variable="<file>",
                title="File not found",
                description=f"Could not read {env_path}",
                recommendation="Check the file path",
            )
        ])

    result = AuditResult(filepath=env_path, total_vars=len(env_vars))

    for name, value in env_vars.items():
        name_lower = name.lower()
        value_lower = value.lower()

        # 1. Weak passwords
        if _is_password_var(name_lower) and value_lower in KNOWN_DEFAULTS:
            result.findings.append(AuditFinding(
                severity=AuditSeverity.CRITICAL,
                variable=name,
                title="Weak/default password detected",
                description=f"'{name}' uses a well-known default value",
                recommendation="Use a strong, randomly generated password (32+ chars)",
            ))

        # 2. Empty secret variables
        elif _is_secret_var(name_lower) and not value:
            result.findings.append(AuditFinding(
                severity=AuditSeverity.HIGH,
                variable=name,
                title="Empty secret variable",
                description=f"'{name}' appears to be a secret but has no value",
                recommendation="Set a strong value or remove if unused",
            ))

        # 3. Short secrets
        elif _is_secret_var(name_lower) and 0 < len(value) < 12:
            result.findings.append(AuditFinding(
                severity=AuditSeverity.HIGH,
                variable=name,
                title="Short secret value",
                description=f"'{name}' has only {len(value)} characters",
                recommendation="Use at least 32 characters for secrets and keys",
            ))

        # 4. Real API key patterns
        for pattern, key_type in API_KEY_PATTERNS:
            if pattern.match(value):
                result.findings.append(AuditFinding(
                    severity=AuditSeverity.CRITICAL,
                    variable=name,
                    title=f"Possible real {key_type} detected",
                    description=f"Value matches the pattern of a {key_type}",
                    recommendation="Ensure this file is in .gitignore and not committed to version control",
                ))
                break

        # 5. Debug mode enabled
        if name_lower in ("debug", "app_debug", "flask_debug", "django_debug"):
            if value_lower in ("true", "1", "yes", "on"):
                result.findings.append(AuditFinding(
                    severity=AuditSeverity.MEDIUM,
                    variable=name,
                    title="Debug mode enabled",
                    description="Debug mode can expose sensitive information",
                    recommendation="Set to false for production environments",
                ))

        # 6. Insecure URLs for sensitive endpoints
        if _is_sensitive_url_var(name_lower) and value.startswith("http://"):
            if "localhost" not in value and "127.0.0.1" not in value:
                result.findings.append(AuditFinding(
                    severity=AuditSeverity.HIGH,
                    variable=name,
                    title="Insecure URL (HTTP instead of HTTPS)",
                    description=f"'{name}' uses HTTP for a non-local endpoint",
                    recommendation="Use HTTPS for production endpoints",
                ))

        # 7. Overly permissive CORS
        if "cors" in name_lower and value == "*":
            result.findings.append(AuditFinding(
                severity=AuditSeverity.MEDIUM,
                variable=name,
                title="Wildcard CORS origin",
                description="CORS is set to allow all origins (*)",
                recommendation="Restrict to specific allowed origins",
            ))

        # 8. Placeholder values that shouldn't be in use
        if any(p in value for p in ["<your_", "CHANGEME", "TODO", "REPLACE_ME"]):
            result.findings.append(AuditFinding(
                severity=AuditSeverity.MEDIUM,
                variable=name,
                title="Placeholder value detected",
                description=f"'{name}' still has a placeholder value",
                recommendation="Replace with an actual value",
            ))

        # 9. Production env with default DB credentials
        env_val = env_vars.get("NODE_ENV", env_vars.get("APP_ENV", env_vars.get("ENVIRONMENT", "")))
        if env_val.lower() in ("production", "prod"):
            if _is_db_var(name_lower) and ("user:password" in value or "root:root" in value):
                result.findings.append(AuditFinding(
                    severity=AuditSeverity.CRITICAL,
                    variable=name,
                    title="Default DB credentials in production",
                    description="Database connection uses default credentials",
                    recommendation="Use unique, strong credentials for production databases",
                ))

    # 10. Check if .env should be in .gitignore
    _check_gitignore(env_path, result)

    return result


def _is_password_var(name: str) -> bool:
    return any(w in name for w in ("password", "passwd", "pass_"))


def _is_secret_var(name: str) -> bool:
    return any(w in name for w in (
        "password", "secret", "token", "key", "api_key", "apikey",
        "private", "credential", "auth_token",
    ))


def _is_sensitive_url_var(name: str) -> bool:
    return any(w in name for w in (
        "api_url", "database_url", "db_url", "webhook", "callback",
        "auth_url", "oauth", "payment",
    ))


def _is_db_var(name: str) -> bool:
    return any(w in name for w in ("database", "db_", "postgres", "mysql", "mongo"))


def _check_gitignore(env_path: str, result: AuditResult) -> None:
    """Check if the env file is likely in .gitignore."""
    import os
    from pathlib import Path

    env_name = Path(env_path).name
    git_dir = Path(env_path).parent

    # Walk up to find .gitignore
    for _ in range(5):
        gitignore = git_dir / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text(encoding="utf-8", errors="replace")
            patterns = [line.strip() for line in content.splitlines()
                        if line.strip() and not line.startswith("#")]
            # Simple check (not full glob matching)
            if env_name in patterns or ".env" in patterns or ".env*" in patterns:
                return
            break
        git_dir = git_dir.parent

    result.findings.append(AuditFinding(
        severity=AuditSeverity.HIGH,
        variable="<file>",
        title=".env file may not be in .gitignore",
        description=f"Could not confirm '{env_name}' is excluded from version control",
        recommendation="Add '.env' to your .gitignore file",
    ))


def format_audit(result: AuditResult) -> str:
    """Format audit results as a readable report."""
    lines = [
        "=" * 60,
        "  ENV SECURITY AUDIT",
        "=" * 60,
        f"  File:        {result.filepath}",
        f"  Variables:   {result.total_vars}",
        f"  Score:       {result.score}/100",
        f"  Findings:    {len(result.findings)}",
        f"    Critical:  {result.critical_count}",
        f"    High:      {result.high_count}",
        "",
    ]

    severity_order = [
        AuditSeverity.CRITICAL,
        AuditSeverity.HIGH,
        AuditSeverity.MEDIUM,
        AuditSeverity.LOW,
        AuditSeverity.INFO,
    ]

    severity_styles = {
        AuditSeverity.CRITICAL: "!!!",
        AuditSeverity.HIGH: " !!",
        AuditSeverity.MEDIUM: "  !",
        AuditSeverity.LOW: "  .",
        AuditSeverity.INFO: "  i",
    }

    for severity in severity_order:
        findings = [f for f in result.findings if f.severity == severity]
        if not findings:
            continue

        lines.append(f"  [{severity.value.upper()}]")
        for finding in findings:
            prefix = severity_styles[severity]
            lines.append(f"  {prefix} {finding.variable}: {finding.title}")
            lines.append(f"      {finding.description}")
            lines.append(f"      -> {finding.recommendation}")
            lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
