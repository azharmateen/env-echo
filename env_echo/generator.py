"""Generate .env files from schema with realistic mock values."""

from __future__ import annotations

import hashlib
import random
import string
from typing import Dict, Optional

from .schema import EnvSchema, VarSpec


# Realistic mock value generators per type
def _random_string(length: int = 32, charset: str = string.ascii_letters + string.digits) -> str:
    return "".join(random.choice(charset) for _ in range(length))


def _mock_value(spec: VarSpec) -> str:
    """Generate a realistic mock value based on the variable spec."""
    var_type = spec.type.lower()

    # If there are enum values, pick one
    if spec.enum_values:
        return spec.default if spec.default and spec.default in spec.enum_values else spec.enum_values[0]

    # If there's a default, use it
    if spec.default is not None:
        return spec.default

    name_lower = spec.name.lower()

    # Type-based generation
    if var_type == "url":
        return _mock_url(name_lower)
    elif var_type == "email":
        return f"admin@example.com"
    elif var_type == "bool":
        return "true"
    elif var_type == "number":
        return _mock_number(spec)
    elif var_type == "port":
        return _mock_port(name_lower)
    elif var_type == "path":
        return _mock_path(name_lower)
    elif var_type == "enum":
        return spec.enum_values[0] if spec.enum_values else "default"
    else:
        # String type - infer from name
        return _mock_string(name_lower, spec)


def _mock_url(name: str) -> str:
    """Generate a mock URL based on variable name."""
    if "database" in name or "db" in name or "postgres" in name:
        return "postgresql://user:password@localhost:5432/myapp_dev"
    if "redis" in name:
        return "redis://localhost:6379/0"
    if "mongo" in name:
        return "mongodb://localhost:27017/myapp_dev"
    if "rabbit" in name or "amqp" in name:
        return "amqp://guest:guest@localhost:5672/"
    if "elastic" in name:
        return "http://localhost:9200"
    if "s3" in name or "bucket" in name:
        return "https://s3.amazonaws.com/my-bucket"
    if "webhook" in name:
        return "https://hooks.example.com/webhook/abc123"
    if "callback" in name or "redirect" in name:
        return "http://localhost:3000/auth/callback"
    if "api" in name or "base" in name:
        return "https://api.example.com/v1"
    if "frontend" in name or "client" in name:
        return "http://localhost:3000"
    return "http://localhost:8000"


def _mock_number(spec: VarSpec) -> str:
    """Generate a mock number."""
    if spec.min_value is not None and spec.max_value is not None:
        return str(int((spec.min_value + spec.max_value) / 2))
    if spec.min_value is not None:
        return str(int(spec.min_value))
    return "1"


def _mock_port(name: str) -> str:
    """Generate a mock port number."""
    port_map = {
        "db": "5432", "database": "5432", "postgres": "5432",
        "redis": "6379", "mongo": "27017",
        "http": "8080", "https": "443",
        "app": "3000", "api": "8000",
        "grpc": "50051", "smtp": "587",
    }
    for key, port in port_map.items():
        if key in name:
            return port
    return "3000"


def _mock_path(name: str) -> str:
    """Generate a mock file path."""
    if "log" in name:
        return "/var/log/myapp/app.log"
    if "upload" in name:
        return "/tmp/uploads"
    if "cert" in name or "ssl" in name:
        return "/etc/ssl/certs/myapp.pem"
    if "key" in name and "priv" in name:
        return "/etc/ssl/private/myapp.key"
    if "data" in name or "storage" in name:
        return "/var/data/myapp"
    return "/tmp/myapp"


def _mock_string(name: str, spec: VarSpec) -> str:
    """Generate a mock string value based on variable name patterns."""
    # API keys and tokens
    if "api_key" in name or "apikey" in name:
        return f"sk-{''.join(random.choices(string.ascii_lowercase + string.digits, k=48))}"
    if "secret" in name and "key" in name:
        return _random_string(64)
    if "token" in name:
        return _random_string(40)
    if "password" in name or "passwd" in name:
        return _random_string(24, string.ascii_letters + string.digits + "!@#$%")
    if "secret" in name:
        return _random_string(48)

    # Common string patterns
    if "host" in name:
        return "localhost"
    if "user" in name or "username" in name:
        return "admin"
    if "name" in name and "app" in name:
        return "myapp"
    if "name" in name and "db" in name:
        return "myapp_dev"
    if "env" in name or "environment" in name or "node_env" in name:
        return "development"
    if "region" in name:
        return "us-east-1"
    if "timezone" in name or "tz" in name:
        return "UTC"
    if "locale" in name or "lang" in name:
        return "en-US"
    if "debug" in name:
        return "true"
    if "log_level" in name or "loglevel" in name:
        return "info"
    if "domain" in name:
        return "example.com"
    if "cors" in name and "origin" in name:
        return "http://localhost:3000"
    if "version" in name:
        return "1.0.0"

    # Default
    return f"your_{name.lower()}_here"


def generate_env(schema: EnvSchema, include_comments: bool = True,
                 include_optional: bool = True) -> str:
    """Generate a .env file from a schema.

    Args:
        schema: The environment schema.
        include_comments: Add descriptive comments.
        include_optional: Include optional variables.

    Returns:
        Complete .env file content.
    """
    lines = []

    if include_comments and schema.name:
        lines.append(f"# {schema.name} Environment Configuration")
        if schema.description:
            lines.append(f"# {schema.description}")
        lines.append(f"# Generated by env-echo v{schema.version}")
        lines.append("")

    groups = schema.groups
    for group_name, variables in groups.items():
        if include_comments:
            lines.append(f"# --- {group_name.upper()} ---")

        for spec in variables:
            if not include_optional and not spec.required:
                continue

            if include_comments:
                parts = []
                if spec.description:
                    parts.append(spec.description)
                if not spec.required:
                    parts.append("optional")
                if spec.type != "string":
                    parts.append(f"type: {spec.type}")
                if spec.enum_values:
                    parts.append(f"values: {', '.join(spec.enum_values)}")
                if spec.secret:
                    parts.append("SECRET")
                if parts:
                    lines.append(f"# {' | '.join(parts)}")

            value = _mock_value(spec)

            # Quote values with spaces or special chars
            if " " in value or "#" in value or "'" in value:
                value = f'"{value}"'

            lines.append(f"{spec.name}={value}")

            if include_comments:
                lines.append("")

    return "\n".join(lines) + "\n"


def generate_example(schema: EnvSchema) -> str:
    """Generate a .env.example file with placeholder values."""
    lines = []
    lines.append("# Environment Configuration Template")
    lines.append("# Copy this file to .env and fill in the values")
    lines.append("")

    groups = schema.groups
    for group_name, variables in groups.items():
        lines.append(f"# --- {group_name.upper()} ---")

        for spec in variables:
            desc = spec.description or f"Your {spec.name}"
            req = " (required)" if spec.required else " (optional)"
            lines.append(f"# {desc}{req}")

            if spec.enum_values:
                lines.append(f"# Allowed values: {', '.join(spec.enum_values)}")

            placeholder = spec.default if spec.default else f"<{spec.type}>"
            lines.append(f"{spec.name}={placeholder}")
            lines.append("")

    return "\n".join(lines) + "\n"
