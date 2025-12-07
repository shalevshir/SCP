# create-pr

## Overview
Push the current branch to remote and automatically create a pull request with comprehensive test results. This command runs all quality checks, displays results, and creates the PR in one automated workflow.

## Automated Workflow

When you run this command, it will:

1. **Validate Branch** - Ensure you're on a feature branch (not main)
2. **Run All Tests** - Execute full test suite with coverage
3. **Run Linters** - Check code quality (ruff, black)
4. **Push Branch** - Push to remote automatically
5. **Generate PR** - Create PR with title/body from commits
6. **Display Results** - Show all test results and PR information

## Prerequisites

- You must be on a feature branch (not `main`)
- You must have commits ready to push
- GitHub CLI (`gh`) must be installed and authenticated

**Install GitHub CLI if needed:**
```bash
brew install gh              # macOS
gh auth login                # Authenticate
```

## Step 1: Run Quality Checks and Push

The command automatically:

1. **Runs Test Suite:**
   ```bash
   poetry run pytest --tb=short -v
   ```
   - Executes all unit and integration tests
   - Shows test results and coverage
   - Fails if any tests fail

2. **Runs Linters:**
   ```bash
   poetry run ruff check .
   poetry run black --check .
   ```
   - Checks code quality
   - Verifies formatting
   - Shows any issues found

3. **Pushes Branch:**
   ```bash
   git push -u origin <branch-name>
   ```
   - Pushes all commits to remote
   - Sets upstream tracking

## Step 2: Generate and Create PR

The command automatically:

1. **Generates PR Title:**
   - Extracted from the most recent commit message
   - Uses commit subject line (first line)
   - Formatted for PR title

2. **Generates PR Body:**
   - Summary from commit messages
   - List of all commits
   - Changed files organized by directory
   - Test results summary
   - Related issues (Closes #123, Fixes #456, etc.)

3. **Creates PR:**
   ```bash
   gh pr create --title "<auto>" --body "<auto>" --base main
   ```

## Step 3: Display Results

After PR creation, the command displays:

### Test Results Summary
```
✅ Tests: 150 passed, 0 failed
📊 Coverage: 85.3%
🔍 Linting: 0 errors, 12 warnings
✨ Formatting: All files formatted correctly
```

### PR Information
```
✅ PR created successfully!
🔗 https://github.com/owner/repo/pull/123
📊 PR #123: feat: add multi-timeframe sync layer
📝 Status: Open
🔍 View: gh pr view
```

### Quality Gate Status
- ✅ All tests passing
- ✅ Code coverage meets threshold
- ✅ Linting passed
- ✅ Formatting correct
- ✅ PR created and ready for review

## Usage

Simply run:
```bash
poetry run python scripts/create_pr_auto.py
```

Or use the Cursor command:
```
/create-pr
```

## What Gets Displayed

1. **Test Execution Results:**
   - Total tests run
   - Tests passed/failed
   - Test failures with details
   - Coverage percentage

2. **Linting Results:**
   - Ruff errors and warnings
   - Black formatting status
   - Files that need attention

3. **PR Creation Results:**
   - PR number and URL
   - PR title
   - PR status
   - Link to view PR

4. **Summary:**
   - Overall status (✅ Ready / ⚠️ Issues Found)
   - Next steps if issues found
   - Commands to view PR details

## Error Handling

If any step fails:

- **Tests Fail:** PR creation is blocked, fix tests and retry
- **Linting Fails:** Warning shown, but PR still created (non-blocking)
- **GitHub CLI Missing:** Clear installation instructions provided
- **PR Already Exists:** Shows existing PR URL instead of creating new one
- **Not on Feature Branch:** Error message with instructions

## Notes

- **Never force-push** to a branch with an open PR
- All test results are displayed before PR creation
- PR body includes test summary for reviewers
- If tests fail, fix issues and re-run the command
- The command ensures all quality gates pass before creating PR

