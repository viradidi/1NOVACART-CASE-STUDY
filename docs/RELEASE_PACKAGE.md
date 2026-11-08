# NovaCart Release Package

The repository includes a GitHub Actions workflow at `.github/workflows/package-novacart-release.yml`.

## What it produces

The workflow packages the current repository contents into `NovaCart-Release.zip` and uploads it as a downloadable GitHub Actions artifact named `NovaCart-Release`.

The package excludes:
- The old `1NOVACART-CASE-STUDY.zip` legacy export.
- Git metadata under `.git/`.
- Generated Python bytecode and `__pycache__` directories.
- Notebook checkpoint and local cache files.
- The output ZIP itself.

The archive includes the current Bronze, Silver, and Gold notebooks; SQL scripts; dashboard export; job configuration template; architecture diagram; and engineering documentation.

## Retrieve the package

Open the repository's **Actions** tab, select the latest successful **Package NovaCart release** run, and download the `NovaCart-Release` artifact. GitHub retains this workflow artifact for 30 days. A package can also be generated for a pull request targeting `main`; push to `main` and manual dispatch remain available for the default-branch release artifact.

The workflow validates notebook and Python syntax, runs the local Spark transformation/configuration tests, builds and inspects the release archive, and uploads the artifact. It does not require an Azure Databricks workspace and does not run the cloud data pipeline.
