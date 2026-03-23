"""Validate .env files against schemas."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from .schema import EnvSchema, VarSpec, parse_env_file


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """A single validation issue."""
    severity: Severity
    variable: str
    message: str
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of validating a .env file."""
    issues: List[ValidationIssue] = field(default_factory=list)
    valid_count: int = 0
    total_checked: int = 0

    @property
    def is_valid(self) -> bool:
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def infos(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.INFO]


def validate(env_path: str, schema: EnvSchema) -> ValidationResult:
    """Validate a .env file against a schema.

    Checks:
    - Required variables are present
    - Type validation (url, email, number, bool, port)
    - Regex pattern validation
    - Enum value validation
    - Range checks for numbers/ports
    - Extra variables not in schema
    """
    result = ValidationResult()

    try:
        env_vars = parse_env_file(env_path)
    except FileNotFoundError:
        result.issues.append(ValidationIssue(
            severity=Severity.ERROR,
            variable="<file>",
            message=f"File not found: {env_path}",
        ))
        return result

    env_names = set(env_vars.keys())
    schema_names = set(v.name for v in schema.variables)

    # Check required variables
    for spec in schema.variables:
        result.total_checked += 1

        if spec.name not in env_vars:
            if spec.required:
                result.issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    variable=spec.name,
                    message=f"Required variable '{spec.name}' is missing",
                    suggestion=f"Add: {spec.name}=<{spec.type}>"
                    + (f" ({spec.description})" if spec.description else ""),
                ))
            else:
                result.issues.append(ValidationIssue(
                    severity=Severity.INFO,
                    variable=spec.name,
                    message=f"Optional variable '{spec.name}' not set"
                    + (f" (default: {spec.default})" if spec.default else ""),
                ))
            continue

        value = env_vars[spec.name]

        # Empty value check
        if not value and spec.required:
            result.issues.append(ValidationIssue(
                severity=Severity.ERROR,
                variable=spec.name,
                message=f"Required variable '{spec.name}' is empty",
            ))
            continue

        # Type validation
        type_issue = _validate_type(spec, value)
        if type_issue:
            result.issues.append(type_issue)
            continue

        # Regex validation
        if spec.validation:
            if not re.match(spec.validation, value):
                result.issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    variable=spec.name,
                    message=f"Value '{value}' does not match pattern: {spec.validation}",
                ))
                continue

        # Enum validation
        if spec.enum_values:
            if value not in spec.enum_values:
                result.issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    variable=spec.name,
                    message=f"Value '{value}' not in allowed values: {', '.join(spec.enum_values)}",
                ))
                continue

        # Range checks
        range_issue = _validate_range(spec, value)
        if range_issue:
            result.issues.append(range_issue)
            continue

        result.valid_count += 1

    # Check for extra variables not in schema
    extra = env_names - schema_names
    for name in sorted(extra):
        result.issues.append(ValidationIssue(
            severity=Severity.WARNING,
            variable=name,
            message=f"Variable '{name}' is not defined in the schema",
            suggestion="Add it to the schema or remove it",
        ))

    return result


def _validate_type(spec: VarSpec, value: str) -> Optional[ValidationIssue]:
    """Validate value against its declared type."""
    var_type = spec.type.lower()

    if var_type == "number":
        try:
            float(value)
        except ValueError:
            return ValidationIssue(
                severity=Severity.ERROR,
                variable=spec.name,
                message=f"Expected number, got: '{value}'",
            )

    elif var_type == "port":
        try:
            port = int(value)
            if port < 0 or port > 65535:
                return ValidationIssue(
                    severity=Severity.ERROR,
                    variable=spec.name,
                    message=f"Port {port} out of range (0-65535)",
                )
        except ValueError:
            return ValidationIssue(
                severity=Severity.ERROR,
                variable=spec.name,
                message=f"Expected port number, got: '{value}'",
            )

    elif var_type == "bool":
        valid_bools = {"true", "false", "1", "0", "yes", "no", "on", "off"}
        if value.lower() not in valid_bools:
            return ValidationIssue(
                severity=Severity.ERROR,
                variable=spec.name,
                message=f"Expected boolean, got: '{value}'",
                suggestion="Use: true, false, 1, 0, yes, no, on, off",
            )

    elif var_type == "url":
        url_pattern = re.compile(
            r"^(https?|ftp|postgresql|postgres|mongodb(\+srv)?|redis|amqp|smtp)://"
        )
        if not url_pattern.match(value):
            return ValidationIssue(
                severity=Severity.ERROR,
                variable=spec.name,
                message=f"Expected URL, got: '{value}'",
                suggestion="URLs must start with a protocol (http://, https://, etc.)",
            )

    elif var_type == "email":
        email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
        if not email_pattern.match(value):
            return ValidationIssue(
                severity=Severity.ERROR,
                variable=spec.name,
                message=f"Expected email address, got: '{value}'",
            )

    elif var_type == "path":
        if not value.startswith("/") and not value.startswith("./") and ":" not in value:
            return ValidationIssue(
                severity=Severity.WARNING,
                variable=spec.name,
                message=f"Path '{value}' does not look like an absolute or relative path",
            )

    return None


def _validate_range(spec: VarSpec, value: str) -> Optional[ValidationIssue]:
    """Validate numeric ranges."""
    if spec.min_value is None and spec.max_value is None:
        return None

    try:
        num = float(value)
    except ValueError:
        return None

    if spec.min_value is not None and num < spec.min_value:
        return ValidationIssue(
            severity=Severity.ERROR,
            variable=spec.name,
            message=f"Value {num} is below minimum {spec.min_value}",
        )

    if spec.max_value is not None and num > spec.max_value:
        return ValidationIssue(
            severity=Severity.ERROR,
            variable=spec.name,
            message=f"Value {num} exceeds maximum {spec.max_value}",
        )

    return None


def validate_standalone(env_path: str) -> ValidationResult:
    """Validate a .env file without a schema (basic checks only)."""
    result = ValidationResult()

    try:
        env_vars = parse_env_file(env_path)
    except FileNotFoundError:
        result.issues.append(ValidationIssue(
            severity=Severity.ERROR,
            variable="<file>",
            message=f"File not found: {env_path}",
        ))
        return result

    for name, value in env_vars.items():
        result.total_checked += 1

        # Check for empty values
        if not value:
            result.issues.append(ValidationIssue(
                severity=Severity.WARNING,
                variable=name,
                message=f"Variable '{name}' has an empty value",
            ))
            continue

        # Check for placeholder values
        placeholders = ["<", "your_", "TODO", "CHANGEME", "xxx", "REPLACE"]
        if any(p in value for p in placeholders):
            result.issues.append(ValidationIssue(
                severity=Severity.WARNING,
                variable=name,
                message=f"Variable '{name}' appears to have a placeholder value: '{value}'",
            ))
            continue

        result.valid_count += 1

    return result
