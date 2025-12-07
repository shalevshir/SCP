# create-branch

## Overview
Create a feature branch with clean commits and open a pull request, ensuring all quality gates are met before proceeding.

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

## Step 3: Push Branch and Create Pull Request

1. Push the branch to remote:
   ```bash
   git push -u origin <branch-name>
   ```

2. Create a pull request using GitHub CLI:
   ```bash
   gh pr create \
     --title "<descriptive PR title>" \
     --body "<detailed description of changes, context, and testing>" \
     --base main
   ```

   **PR Title Guidelines:**
   - Use imperative mood: "Add multi-timeframe sync" not "Added multi-timeframe sync"
   - Be specific and concise
   - Include ticket/issue number if applicable

   **PR Body Template:**
   ```markdown
   ## Summary
   Brief description of what this PR does.

   ## Changes
   - Change 1
   - Change 2
   - Change 3

   ## Testing
   - How was this tested?
   - What test cases were added/updated?

   ## Related Issues
   Closes #123
   ```

3. **Optional PR Flags:**
   - `--draft` - Mark PR as draft (work in progress)
   - `--assignee @username` - Assign specific reviewers
   - `--reviewer @username` - Request review from specific users
   - `--label "label1,label2"` - Add labels (e.g., "enhancement", "bugfix")
   - `--milestone "<milestone>"` - Associate with a milestone

   Example with options:
   ```bash
   gh pr create \
     --title "feat: add multi-timeframe sync layer" \
     --body "$(cat <<'EOF'
   ## Summary
   Implements multi-timeframe synchronization for GC and DXY data alignment.

   ## Changes
   - Add MultiTimeframeSync class
   - Integrate with backtester pipeline
   - Add comprehensive tests

   ## Testing
   - All unit tests pass
   - Integration tests added for sync scenarios
   EOF
   )" \
     --base main \
     --label "enhancement,backtester" \
     --reviewer @username
   ```

## Step 4: Verify PR Creation

After creating the PR:
1. Verify the PR was created successfully: `gh pr view`
2. Check that CI/CD pipelines are running
3. Ensure all required checks are passing
4. Address any review feedback promptly

## Notes

- **Never force-push** to a branch with an open PR
- Keep commits focused and atomic
- Rebase (don't merge) `main` into your branch if needed: `git rebase origin/main`
- Update the PR description if significant changes are made after initial creation