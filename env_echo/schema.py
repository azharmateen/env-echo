"""Schema definition: YAML format for env variable specifications."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class VarSpec:
    """Specification for a single environment variable."""
    name: str
    type: str = "string"         # string, number, url, email, bool, port, path, enum
    required: bool = True
    default: Optional[str] = None
    description: str = ""
    validation: Optional[str] = None  # regex pattern
    enum_values: List[str] = field(default_factory=list)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    secret: bool = False          # marks as sensitive (passwords, keys, tokens)
    group: str = "default"        # logical grouping


@dataclass
class EnvSchema:
    """Complete schema for an environment configuration."""
    name: str = ""
    version: str = "1.0"
    description: str = ""
    variables: List[VarSpec] = field(default_factory=list)

    @property
    def required_vars(self) -> List[VarSpec]:
        return [v for v in self.variables if v.required]

    @property
    def optional_vars(self) -> List[VarSpec]:
        return [v for v in self.variables if not v.required]

    @property
    def groups(self) -> Dict[str, List[VarSpec]]:
        groups: Dict[str, List[VarSpec]] = {}
        for v in self.variables:
            groups.setdefault(v.group, []).append(v)
        return groups


def load_schema(path: str) -> EnvSchema:
    """Load an env schema from a YAML file.

    Expected YAML format:
    ```yaml
    name: "My App"
    version: "1.0"
    description: "Environment configuration for My App"
    variables:
      - name: DATABASE_URL
        type: url
        required: true
        description: "PostgreSQL connection URL"
        group: database
        secret: true

      - name: PORT
        type: port
        required: false
        default: "3000"
        description: "Server port"
        min: 1024
        max: 65535

      - name: LOG_LEVEL
        type: enum
        enum_values: [debug, info, warning, error, critical]
        default: "info"
    ```
    """
    content = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    if not isinstance(data, dict):
        raise ValueError(f"Schema file must be a YAML mapping, got {type(data).__name__}")

    schema = EnvSchema(
        name=data.get("name", ""),
        version=str(data.get("version", "1.0")),
        description=data.get("description", ""),
    )

    for var_data in data.get("variables", []):
        if not isinstance(var_data, dict) or "name" not in var_data:
            continue

        spec = VarSpec(
            name=var_data["name"],
            type=var_data.get("type", "string"),
            required=var_data.get("required", True),
            default=str(var_data["default"]) if "default" in var_data else None,
            description=var_data.get("description", ""),
            validation=var_data.get("validation", None),
            enum_values=[str(v) for v in var_data.get("enum_values", [])],
            min_value=var_data.get("min", var_data.get("min_value")),
            max_value=var_data.get("max", var_data.get("max_value")),
            secret=var_data.get("secret", False),
            group=var_data.get("group", "default"),
        )

        # Auto-detect secret vars by name
        if not spec.secret:
            secret_patterns = [
                "password", "secret", "token", "key", "api_key",
                "apikey", "private", "credential",
            ]
            name_lower = spec.name.lower()
            if any(p in name_lower for p in secret_patterns):
                spec.secret = True

        schema.variables.append(spec)

    return schema


def schema_to_yaml(schema: EnvSchema) -> str:
    """Serialize a schema back to YAML format."""
    data: Dict[str, Any] = {
        "name": schema.name,
        "version": schema.version,
        "description": schema.description,
        "variables": [],
    }

    for var in schema.variables:
        var_data: Dict[str, Any] = {"name": var.name, "type": var.type}
        if not var.required:
            var_data["required"] = False
        if var.default is not None:
            var_data["default"] = var.default
        if var.description:
            var_data["description"] = var.description
        if var.validation:
            var_data["validation"] = var.validation
        if var.enum_values:
            var_data["enum_values"] = var.enum_values
        if var.min_value is not None:
            var_data["min"] = var.min_value
        if var.max_value is not None:
            var_data["max"] = var.max_value
        if var.secret:
            var_data["secret"] = True
        if var.group != "default":
            var_data["group"] = var.group
        data["variables"].append(var_data)

    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def parse_env_file(path: str) -> Dict[str, str]:
    """Parse a .env file into a dict of name -> value."""
    result: Dict[str, str] = {}
    content = Path(path).read_text(encoding="utf-8")

    for line_num, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        # Handle export prefix
        if stripped.startswith("export "):
            stripped = stripped[7:].strip()

        # Split on first =
        if "=" not in stripped:
            continue

        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()

        # Remove quotes
        if len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]

        result[key] = value

    return result
