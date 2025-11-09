# GitHub Configuration

This directory contains GitHub-specific configuration files for the SCP Trading Bot project.

## Files

### Workflows

- **`workflows/ci.yml`** - Continuous Integration workflow
  - Runs tests with coverage
  - Runs linters (ruff, mypy)
  - Checks code formatting (black, isort)
  - Posts coverage reports and test results to PRs
  - Runs on every push to `main` and all pull requests

### Documentation

Branch protection setup instructions are included below and in the [Running Tests](../docs/07-running-tests.md#ci-requirements) documentation.

## Quick Links

- [CI Workflow](workflows/ci.yml)
- [Running Tests Documentation](../docs/07-running-tests.md)
- [Development Workflow](../docs/05-development-workflow.md)

## CI Status Checks

The CI workflow provides three status checks:

1. **Run Tests** ✅ **REQUIRED** - Full test suite with coverage (blocks merge)
2. **Run Linters** 📊 Recommended - Code quality checks (ruff + mypy)
3. **Check Formatting** 📊 Recommended - Code style checks (black + isort)

Only tests are required to pass before merging (when branch protection is enabled).

## Setting Up Branch Protection

To require tests before merging:

1. Go to repository **Settings** → **Branches**
2. Click **"Add rule"** for `main` branch
3. Enable required status checks:
   - ☑️ **Require a pull request before merging**
   - ☑️ **Require status checks to pass before merging**
     - Add: `Run Tests` (required)
   - ☑️ **Include administrators** (recommended)
4. **Save changes**

**Note:** Linting and formatting checks run but don't block merges. They're strongly recommended to follow.

## CI Features

✅ **Automated Testing** - Runs on every PR and push to main
✅ **Coverage Reporting** - Posts coverage changes as PR comments
✅ **Test Results** - Shows failed tests with details
✅ **Artifact Storage** - Saves test results and logs (30 days)
✅ **Parallel Jobs** - Tests, linting, and formatting run concurrently
✅ **Fast Feedback** - Average runtime ~2-3 minutes

## Local Development

Run the same checks locally before pushing:

```bash
# Run all checks
make check

# Run individual checks
make test           # Run tests
make test-coverage  # Run tests with coverage
make lint           # Run linters
make format         # Format code
```

## Troubleshooting

If CI fails:

1. Check the "Checks" tab on your PR
2. Click "Details" on the failed check
3. Review the error logs
4. Fix the issue locally
5. Push the fix - CI will automatically re-run

Common fixes:

```bash
# Fix formatting
make format

# Fix linting errors (some auto-fixable)
ruff check --fix .

# Run tests locally to debug
make test-verbose
```

---

For more information, see the [project documentation](../docs/).

