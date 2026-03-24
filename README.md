# env-echo

[![Built with Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-blue?logo=anthropic&logoColor=white)](https://claude.ai/code)


Offline environment variable manager: generate, validate, mock, and audit .env files. No cloud dependencies, no AI -- just solid local tooling.

## Features

- **Generate**: Create .env files from YAML schemas with realistic mock values
- **Validate**: Check .env files against schemas (types, required, ranges, enums, regex)
- **Diff**: Compare two .env files, highlight security-relevant changes
- **Audit**: Security scan for weak passwords, exposed keys, debug mode, insecure URLs
- **Templates**: Output as .env, .env.example, docker-compose, Kubernetes ConfigMap/Secret, GitHub Actions

## Installation

```bash
pip install -e .
```

## Quick Start

### 1. Create a schema

```yaml
# schema.yaml
name: "My App"
version: "1.0"
variables:
  - name: DATABASE_URL
    type: url
    required: true
    description: "PostgreSQL connection string"
    group: database
    secret: true

  - name: PORT
    type: port
    default: "3000"
    required: false
    min: 1024
    max: 65535

  - name: LOG_LEVEL
    type: enum
    enum_values: [debug, info, warning, error]
    default: "info"

  - name: API_KEY
    type: string
    required: true
    secret: true
    description: "External API key"
```

### 2. Generate a .env file

```bash
env-echo generate --schema schema.yaml
env-echo generate --schema schema.yaml --output .env
env-echo generate --schema schema.yaml --format example --output .env.example
env-echo generate --schema schema.yaml --format k8s-configmap
```

### 3. Validate

```bash
env-echo validate .env --schema schema.yaml
env-echo validate .env  # basic checks without schema
```

### 4. Diff environments

```bash
env-echo diff .env.dev .env.prod
env-echo diff .env.dev .env.prod --hide-values  # redact secrets
```

### 5. Security audit

```bash
env-echo audit .env
```

## Output Formats

| Format | Flag | Description |
|--------|------|-------------|
| `.env` | `--format env` | Standard dotenv with comments |
| `.env.example` | `--format example` | Placeholders only |
| Docker Compose | `--format docker-compose` | `environment:` YAML block |
| Docker env_file | `--format docker-env` | Bare key=value (no quotes/comments) |
| K8s ConfigMap | `--format k8s-configmap` | ConfigMap + Secret YAML |
| K8s Deployment | `--format k8s-env` | Container `env:` with refs |
| GitHub Actions | `--format github-actions` | `env:` block with `${{ secrets.* }}` |

## Schema Types

| Type | Validation |
|------|-----------|
| `string` | Any text |
| `number` | Numeric (float/int), supports `min`/`max` |
| `url` | Must start with protocol (http, https, postgresql, etc.) |
| `email` | Valid email format |
| `bool` | true/false/yes/no/on/off/1/0 |
| `port` | Integer 0-65535 |
| `path` | Absolute or relative file path |
| `enum` | Must be one of `enum_values` |

## License

MIT
