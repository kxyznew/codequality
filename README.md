# Codequality

Codequality is a small, multi-language quality orchestrator packaged as a GitHub Action. It detects common project types, runs the configured linters available for each one, writes a Markdown summary, and produces SARIF 2.1.0 results for GitHub code scanning.

## Use the GitHub Action

Add this to a workflow in the repository you want to scan:

```yaml
name: Code quality

on:
  push:
  pull_request:

permissions:
  contents: read
  security-events: write

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: kxyznew/codequality/action@v1
        with:
          fail-on: warning
          upload-sarif: true
```

The workflow needs `security-events: write` for SARIF uploads. GitHub code scanning is available for public repositories and for eligible private repositories where code security is enabled. Set `upload-sarif: false` if you only want the workflow summary and SARIF file left in the checkout.

Inputs:

| Input | Default | Description |
|---|---|---|
| `path` | `.` | Repository directory to scan, relative to the checkout. |
| `fail-on` | `warning` | Fail on `error`, `warning`, or `none`. Scanner execution errors always fail the step. |
| `sarif-file` | `.codequality/results.sarif` | SARIF output path relative to the checkout. |
| `upload-sarif` | `true` | Upload the SARIF file to GitHub code scanning. |

Outputs:

| Output | Description |
|---|---|
| `findings-count` | Total findings written to SARIF. |
| `sarif-file` | SARIF output path. |

## Supported scanners

| Project content | Scanner | Behavior |
|---|---|---|
| Python files | Ruff | Installed with Codequality; reports Ruff lint findings. |
| JavaScript / TypeScript files | ESLint | Runs a project-local or PATH-installed ESLint when an ESLint config is present. |
| Go module (`go.mod`) | `go vet` | Runs once for each Go module when Go is installed. |
| Rust crate (`Cargo.toml`) | Clippy | Runs once for each Rust crate when Cargo and Clippy are installed. |
| Shell scripts (`*.sh`) | ShellCheck | Runs when ShellCheck is installed. |

Codequality does not install or rewrite your JavaScript, Go, Rust, or Shell dependencies. If a project file is present but its optional scanner or config is missing, the action records that in the workflow summary and continues.

## Run locally

Python 3.10 or newer is required.

```bash
python -m pip install -e .
codequality scan --workspace . --sarif .codequality/results.sarif --fail-on warning
```

## Releases

This repository is published at [github.com/kxyznew/codequality](https://github.com/kxyznew/codequality). The `v1.0.0` release is the first version, and the `v1` major-version tag points to the same source state. Use `kxyznew/codequality/action@v1` in workflows to follow compatible v1 updates.

To publish a fork, create an empty repository on GitHub and run `bootstrap.sh` with `REPO_URL` set to your new repository. The script initializes Git, commits these files, and pushes the `main` branch; it does not create a GitHub repository or release tags.

## License

MIT. See [LICENSE](LICENSE).
