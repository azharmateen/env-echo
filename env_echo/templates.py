"""Output templates: .env, .env.example, docker-compose, k8s ConfigMap."""

from __future__ import annotations

from typing import Dict, List

from .schema import EnvSchema, VarSpec


def to_env(schema: EnvSchema, values: Dict[str, str]) -> str:
    """Generate a .env file with given values."""
    lines: List[str] = []

    for group_name, variables in schema.groups.items():
        lines.append(f"# {group_name}")
        for spec in variables:
            value = values.get(spec.name, spec.default or "")
            if " " in value or "#" in value:
                value = f'"{value}"'
            lines.append(f"{spec.name}={value}")
        lines.append("")

    return "\n".join(lines)


def to_env_example(schema: EnvSchema) -> str:
    """Generate a .env.example file with placeholders."""
    lines: List[str] = []
    lines.append("# Environment Configuration")
    lines.append("# Copy to .env and fill in the values")
    lines.append("")

    for group_name, variables in schema.groups.items():
        lines.append(f"# === {group_name.upper()} ===")
        for spec in variables:
            req = "REQUIRED" if spec.required else "optional"
            if spec.description:
                lines.append(f"# {spec.description} ({req})")
            else:
                lines.append(f"# ({req})")

            if spec.enum_values:
                lines.append(f"# Options: {', '.join(spec.enum_values)}")

            if spec.secret:
                placeholder = "<secret>"
            elif spec.default:
                placeholder = spec.default
            else:
                placeholder = f"<{spec.type}>"

            lines.append(f"{spec.name}={placeholder}")
        lines.append("")

    return "\n".join(lines)


def to_docker_compose_env(schema: EnvSchema,
                          values: Dict[str, str] | None = None) -> str:
    """Generate docker-compose environment section YAML.

    Produces:
    ```yaml
    environment:
      - DATABASE_URL=postgresql://...
      - PORT=3000
    ```
    """
    lines: List[str] = ["environment:"]

    for spec in schema.variables:
        value = ""
        if values and spec.name in values:
            value = values[spec.name]
        elif spec.default:
            value = spec.default

        if spec.secret and not value:
            # Use env_file reference for secrets
            lines.append(f"  - {spec.name}=${{{{  {spec.name}  }}}}")
        else:
            lines.append(f"  - {spec.name}={value}")

    return "\n".join(lines)


def to_docker_env_file(schema: EnvSchema,
                       values: Dict[str, str] | None = None) -> str:
    """Generate a Docker env_file compatible file (no quotes, no comments)."""
    lines: List[str] = []

    for spec in schema.variables:
        value = ""
        if values and spec.name in values:
            value = values[spec.name]
        elif spec.default:
            value = spec.default
        lines.append(f"{spec.name}={value}")

    return "\n".join(lines)


def to_k8s_configmap(schema: EnvSchema, name: str = "app-config",
                     namespace: str = "default",
                     values: Dict[str, str] | None = None) -> str:
    """Generate a Kubernetes ConfigMap YAML.

    Non-secret variables go into ConfigMap data.
    Secret variables are noted as needing a separate Secret resource.
    """
    lines: List[str] = [
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        f"  name: {name}",
        f"  namespace: {namespace}",
        "data:",
    ]

    secret_vars: List[VarSpec] = []

    for spec in schema.variables:
        if spec.secret:
            secret_vars.append(spec)
            continue

        value = ""
        if values and spec.name in values:
            value = values[spec.name]
        elif spec.default:
            value = spec.default

        # YAML string formatting
        if any(c in value for c in ":#{}[]|>&*!%@`"):
            lines.append(f'  {spec.name}: "{value}"')
        else:
            lines.append(f"  {spec.name}: \"{value}\"")

    if secret_vars:
        lines.append("")
        lines.append("---")
        lines.append("# Secret variables - create a separate Secret resource")
        lines.append("apiVersion: v1")
        lines.append("kind: Secret")
        lines.append("metadata:")
        lines.append(f"  name: {name}-secrets")
        lines.append(f"  namespace: {namespace}")
        lines.append("type: Opaque")
        lines.append("stringData:")

        for spec in secret_vars:
            value = ""
            if values and spec.name in values:
                value = values[spec.name]
            lines.append(f'  {spec.name}: "{value}"')

    return "\n".join(lines)


def to_k8s_deployment_env(schema: EnvSchema, configmap_name: str = "app-config",
                          secret_name: str = "app-config-secrets") -> str:
    """Generate Kubernetes Deployment env section referencing ConfigMap/Secret.

    Produces the `env:` block for a container spec.
    """
    lines: List[str] = ["env:"]

    for spec in schema.variables:
        lines.append(f"  - name: {spec.name}")
        if spec.secret:
            lines.append("    valueFrom:")
            lines.append("      secretKeyRef:")
            lines.append(f"        name: {secret_name}")
            lines.append(f"        key: {spec.name}")
        else:
            lines.append("    valueFrom:")
            lines.append("      configMapKeyRef:")
            lines.append(f"        name: {configmap_name}")
            lines.append(f"        key: {spec.name}")

    return "\n".join(lines)


def to_github_actions_env(schema: EnvSchema) -> str:
    """Generate GitHub Actions env section YAML."""
    lines: List[str] = ["env:"]

    for spec in schema.variables:
        if spec.secret:
            lines.append(f"  {spec.name}: ${{{{ secrets.{spec.name} }}}}")
        elif spec.default:
            lines.append(f"  {spec.name}: \"{spec.default}\"")
        else:
            lines.append(f"  {spec.name}: ${{{{ vars.{spec.name} }}}}")

    return "\n".join(lines)
