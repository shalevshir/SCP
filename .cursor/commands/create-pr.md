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

## What Happens

The command automatically runs tests, linters, pushes your branch, and creates a PR. You'll see:

1. **Test execution** - Full test suite runs and results are displayed
2. **Linting checks** - Code quality and formatting are verified
3. **Branch push** - Your branch is pushed to remote
4. **PR creation** - PR is created with title/body generated from your commits
5. **Results summary** - Complete status of all checks and PR information

You'll see output like this:

```
🧪 Running tests...
[test output]
✅ Tests: 150 passed, 0 failed
📊 Coverage: 85.3%

🔍 Running linters...
[linter output]
✅ Linting: All checks passed

📤 Pushing branch...
✅ Branch pushed successfully

🔨 Creating PR...
✅ PR CREATED SUCCESSFULLY!
🔗 https://github.com/owner/repo/pull/123

📊 Summary:
   ✅ Tests: 150 passed, 0 failed
   📊 Coverage: 85.3%
   🔍 Linting: 0 errors, 12 warnings
   ✨ Formatting: ✅ OK
📝 View PR: gh pr view
```

## Usage

Simply run:
```bash
poetry run python scripts/create_pr_auto.py
```

Or use the Cursor command:
```
/create-pr
```

## Output Example

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

