# create-branch

## Overview
Create a feature branch and generate clean, logically separated commits. This command focuses on branch creation and commit management.

## Prerequisites: Definition of Done Checklist

Before creating a branch, validate that the code satisfies the full Definition of Done:

- [ ] All required documentation is written and updated (README, docstrings, changelog if applicable)
- [ ] All unit/integration tests pass: `poetry run pytest`
- [ ] Code coverage meets the project's threshold
- [ ] Linting passes: `poetry run ruff check .` and `poetry run black --check .`
- [ ] Type checking passes (if applicable): `poetry run mypy .`
- [ ] No secrets or sensitive data are committed
- [ ] Code follows project style guidelines and best practices

**If any criteria are not met, fix issues before proceeding.**

## Step 1: Create and Switch to Feature Branch

1. Ensure you're on `main` and up to date:
   ```bash
   git checkout main
   git pull origin main
   ```

2. Create a descriptive branch name following the project's convention:
   ```bash
   git checkout -b <branch-type>/<short-description>
   ```
   Examples:
   - `feature/multi-timeframe-sync-layer`
   - `fix/vwap-calculation-edge-case`
   - `refactor/backtester-pipeline`

## Step 2: Generate Clean, Logically Separated Commits

Create commits that tell a clear story. Each commit should:
- Represent a single logical change
- Have a clear, descriptive commit message
- Pass all tests independently (if possible)

Commit message format:
```
<type>: <short summary>

<optional detailed explanation>

- What changed and why
- Any breaking changes or migration notes
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

Example:
```bash
git add <files>
git commit -m "feat: add multi-timeframe sync layer

- Implement MultiTimeframeSync class for aligning GC and DXY data
- Add validation for timeframe alignment
- Update backtester to use new sync layer

Closes #123"
```

## Step 3: Verify Your Commits

review your commits are ready to push:
```bash
git log --oneline main..HEAD  # View commits not in main
git status                     # Check for uncommitted changes
```


## Notes

- **Never force-push** to a branch with an open PR
- Keep commits focused and atomic
- Rebase (don't merge) `main` into your branch if needed: `git rebase origin/main`
- Update the PR description if significant changes are made after initial creation