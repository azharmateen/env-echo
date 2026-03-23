"""Click CLI for env-echo."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .schema import load_schema, parse_env_file
from .generator import generate_env, generate_example
from .validator import validate, validate_standalone, Severity
from .differ import diff_env_files, format_diff
from .auditor import audit, format_audit
from .templates import (
    to_env_example,
    to_docker_compose_env,
    to_docker_env_file,
    to_k8s_configmap,
    to_k8s_deployment_env,
    to_github_actions_env,
)

console = Console()

SEVERITY_STYLES = {
    Severity.ERROR: "red",
    Severity.WARNING: "yellow",
    Severity.INFO: "dim",
}


@click.group()
@click.version_option(version="1.0.0", prog_name="env-echo")
def main():
    """Offline environment variable manager: generate, validate, mock, and audit .env files."""
    pass


@main.command()
@click.option("--schema", "-s", "schema_path", required=True,
              type=click.Path(exists=True), help="Path to schema YAML file.")
@click.option("--output", "-o", default=None, help="Output file path (default: stdout).")
@click.option("--format", "fmt", type=click.Choice([
    "env", "example", "docker-compose", "docker-env", "k8s-configmap",
    "k8s-env", "github-actions",
]), default="env", help="Output format.")
@click.option("--no-comments", is_flag=True, help="Omit comments from output.")
@click.option("--name", default="app-config", help="Name for k8s resources.")
def generate(schema_path: str, output: str, fmt: str,
             no_comments: bool, name: str):
    """Generate .env file from a schema definition.

    Produces realistic mock values appropriate to each variable type.
    """
    schema = load_schema(schema_path)

    if fmt == "env":
        content = generate_env(schema, include_comments=not no_comments)
    elif fmt == "example":
        content = to_env_example(schema)
    elif fmt == "docker-compose":
        content = to_docker_compose_env(schema)
    elif fmt == "docker-env":
        content = to_docker_env_file(schema)
    elif fmt == "k8s-configmap":
        content = to_k8s_configmap(schema, name=name)
    elif fmt == "k8s-env":
        content = to_k8s_deployment_env(schema, configmap_name=name)
    elif fmt == "github-actions":
        content = to_github_actions_env(schema)
    else:
        content = generate_env(schema)

    if output:
        Path(output).write_text(content, encoding="utf-8")
        console.print(f"[green]Generated {output}[/green]")
    else:
        console.print(content)


@main.command("validate")
@click.argument("env_file", type=click.Path(exists=True))
@click.option("--schema", "-s", "schema_path", default=None,
              type=click.Path(exists=True), help="Schema file for validation.")
def validate_cmd(env_file: str, schema_path: str):
    """Validate a .env file, optionally against a schema.

    Without --schema, performs basic checks (empty values, placeholders).
    With --schema, validates types, required vars, ranges, and enums.
    """
    if schema_path:
        schema = load_schema(schema_path)
        result = validate(env_file, schema)
    else:
        result = validate_standalone(env_file)

    # Display results
    console.print(f"\n[bold]Validating:[/bold] {env_file}")
    if schema_path:
        console.print(f"[bold]Schema:[/bold] {schema_path}")
    console.print()

    if result.is_valid and not result.warnings:
        console.print("[green]All checks passed.[/green]")
    else:
        table = Table(title="Validation Results")
        table.add_column("Severity", width=10)
        table.add_column("Variable", min_width=20)
        table.add_column("Message", min_width=40)
        table.add_column("Suggestion", min_width=20)

        for issue in result.issues:
            style = SEVERITY_STYLES.get(issue.severity, "white")
            table.add_row(
                f"[{style}]{issue.severity.value.upper()}[/{style}]",
                issue.variable,
                issue.message,
                issue.suggestion or "",
            )

        console.print(table)

    console.print(f"\n[dim]Checked: {result.total_checked} | "
                  f"Valid: {result.valid_count} | "
                  f"Errors: {len(result.errors)} | "
                  f"Warnings: {len(result.warnings)}[/dim]")

    if result.errors:
        sys.exit(1)


@main.command()
@click.argument("env_file", default=".env", type=click.Path(exists=True))
def mock(env_file: str):
    """Show mock/placeholder info for a .env file.

    Reads an existing .env file and displays its structure.
    """
    env_vars = parse_env_file(env_file)

    table = Table(title=f"Variables in {env_file}")
    table.add_column("Name", style="cyan")
    table.add_column("Value", max_width=50)
    table.add_column("Type (guessed)", style="dim")

    for name, value in sorted(env_vars.items()):
        guessed_type = _guess_type(name, value)
        # Mask potential secrets
        display_value = value
        if _looks_secret(name):
            if len(value) > 8:
                display_value = value[:4] + "*" * (len(value) - 8) + value[-4:]
            else:
                display_value = "***"
        table.add_row(name, display_value, guessed_type)

    console.print(table)
    console.print(f"\n[dim]Total: {len(env_vars)} variables[/dim]")


@main.command("diff")
@click.argument("file_a", type=click.Path(exists=True))
@click.argument("file_b", type=click.Path(exists=True))
@click.option("--show-unchanged", is_flag=True, help="Include unchanged variables.")
@click.option("--show-values/--hide-values", default=True,
              help="Show or hide actual values (secrets are always redacted when hidden).")
def diff_cmd(file_a: str, file_b: str, show_unchanged: bool, show_values: bool):
    """Diff two .env files to find differences.

    Shows added, removed, and changed variables with security warnings.
    """
    result = diff_env_files(file_a, file_b, show_values=show_values)
    output = format_diff(result, show_unchanged=show_unchanged)
    console.print(f"\n{output}")


@main.command("audit")
@click.argument("env_file", type=click.Path(exists=True))
def audit_cmd(env_file: str):
    """Security audit of a .env file.

    Detects weak passwords, default credentials, exposed API keys,
    debug mode, insecure URLs, and missing .gitignore entries.
    """
    result = audit(env_file)
    output = format_audit(result)
    console.print(f"\n{output}")

    if result.critical_count > 0:
        sys.exit(2)
    elif result.high_count > 0:
        sys.exit(1)


def _guess_type(name: str, value: str) -> str:
    """Guess the type of a variable from its name and value."""
    name_lower = name.lower()

    if value.lower() in ("true", "false", "yes", "no", "on", "off", "1", "0"):
        return "bool"
    if "://" in value:
        return "url"
    if "@" in value and "." in value.split("@")[-1]:
        return "email"
    if value.startswith("/") or value.startswith("./"):
        return "path"
    try:
        port = int(value)
        if "port" in name_lower or 1 <= port <= 65535:
            return "port"
        return "number"
    except ValueError:
        pass
    try:
        float(value)
        return "number"
    except ValueError:
        pass

    if _looks_secret(name):
        return "secret"

    return "string"


def _looks_secret(name: str) -> bool:
    """Check if a variable name looks like a secret."""
    secret_words = {
        "password", "secret", "token", "key", "api_key", "apikey",
        "private", "credential", "auth",
    }
    name_lower = name.lower()
    return any(w in name_lower for w in secret_words)


if __name__ == "__main__":
    main()
