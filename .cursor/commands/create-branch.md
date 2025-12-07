# create-branch

## Overview
Create a feature branch with clean commits and **automatically** open a pull request, ensuring all quality gates are met before proceeding. The command handles PR creation automatically—no manual steps or options to choose from.

## Automated Workflow

When you run this command, it will:

1. **Validate Prerequisites** - Check all Definition of Done criteria
2. **Create/Verify Branch** - Ensure you're on the correct branch
3. **Generate Commits** - Guide you through creating clean commits
4. **Push to Remote** - Push the branch automatically
5. **Create PR Automatically** - Generate PR title/body from commits and create PR
6. **Display Results** - Show PR URL, number, and status immediately

**No manual PR creation needed** - everything is automated based on your commits.

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

## Step 3: Push Branch and Automatically Create Pull Request

1. Push the branch to remote:
   ```bash
   git push -u origin <branch-name>
   ```

2. **Automatically create a pull request:**
   
   Run the automated PR creation script:
   ```bash
   poetry run python scripts/create_pr_auto.py
   ```
   
   The script will:
   - Check if GitHub CLI (`gh`) is installed
   - Generate PR title from the most recent commit message
   - Generate PR body from commit messages and changed files
   - Create the PR automatically and display the results
   
   **If GitHub CLI is not installed:**
   - Install it: `brew install gh` (macOS) or follow [GitHub CLI installation guide](https://cli.github.com/manual/installation)
   - Authenticate: `gh auth login`
   - Then re-run the script
   
   **PR Title Generation:**
   - Extracted from the most recent commit message
   - Uses the commit subject line (first line)
   - Automatically formatted for PR title
   
   **PR Body Generation:**
   - Summary from commit messages
   - List of changes from commit history
   - Testing information from commit messages
   - Related issues extracted from commit messages (Closes #123, Fixes #456, etc.)
   
   **Automatic PR Creation:**
   ```bash
   # The command automatically:
   # 1. Gets current branch name
   # 2. Extracts commit messages
   # 3. Generates PR title and body
   # 4. Creates PR with: gh pr create --title "<auto>" --body "<auto>" --base main
   # 5. Displays PR URL and status
   ```
   
   **Result Display:**
   After PR creation, you'll see:
   - PR number and URL
   - PR title
   - PR status (draft/open)
   - Link to view the PR

## Step 4: Verify PR Creation (Automatic)

The command automatically verifies PR creation and displays:
- ✅ PR creation status (success/failure)
- 🔗 PR URL for viewing in browser
- 📊 PR number and current status
- 🔍 Link to CI/CD status (if available)

**Manual Verification (if needed):**
```bash
gh pr view                    # View PR details
gh pr checks                  # Check CI/CD status
gh pr list --head <branch>    # List PRs for current branch
```

## Notes

- **Never force-push** to a branch with an open PR
- Keep commits focused and atomic
- Rebase (don't merge) `main` into your branch if needed: `git rebase origin/main`
- Update the PR description if significant changes are made after initial creation