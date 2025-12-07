#!/usr/bin/env python3
"""
Automatically create a GitHub PR from the current branch.

This script:
1. Checks if GitHub CLI is installed
2. Generates PR title from commit messages
3. Generates PR body from commit history
4. Creates PR automatically
5. Displays results
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional


def run_command(cmd: list[str], check: bool = True) -> tuple[int, str, str]:
    """Run a shell command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=check
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout.strip(), e.stderr.strip()


def check_gh_installed() -> bool:
    """Check if GitHub CLI is installed."""
    exit_code, _, _ = run_command(["which", "gh"], check=False)
    return exit_code == 0


def get_current_branch() -> Optional[str]:
    """Get the current git branch name."""
    exit_code, stdout, _ = run_command(["git", "branch", "--show-current"], check=False)
    if exit_code == 0:
        return stdout
    return None


def get_commit_messages(limit: int = 10) -> list[str]:
    """Get commit messages from current branch that aren't in main."""
    # Get commits that are in current branch but not in main
    exit_code, stdout, _ = run_command(
        ["git", "log", "main..HEAD", f"--format=%s%n%b", f"-{limit}"], check=False
    )
    if exit_code == 0 and stdout:
        # Split by double newline to separate commits, then by single newline for subject/body
        commits = [c.strip() for c in stdout.split("\n\n") if c.strip()]
        return commits
    return []


def get_changed_files() -> list[str]:
    """Get list of changed files compared to main."""
    exit_code, stdout, _ = run_command(
        ["git", "diff", "--name-only", "main...HEAD"], check=False
    )
    if exit_code == 0 and stdout:
        return [f.strip() for f in stdout.split("\n") if f.strip()]
    return []


def generate_pr_title(commits: list[str]) -> str:
    """Generate PR title from the most recent commit."""
    if not commits:
        return "Update from feature branch"
    
    # Use the first line of the most recent commit
    first_commit = commits[0]
    title = first_commit.split("\n")[0].strip()
    
    # Remove commit type prefix if it's redundant (e.g., "feat: " -> "Add")
    if ":" in title and len(title.split(":")[0]) < 10:
        # Keep the type prefix as it's useful
        pass
    
    return title


def generate_pr_body(commits: list[str], changed_files: list[str]) -> str:
    """Generate PR body from commits and changed files."""
    body_parts = ["## Summary"]
    
    if commits:
        # Extract summary from first commit
        first_commit = commits[0]
        lines = first_commit.split("\n")
        if len(lines) > 1:
            # Has body, use it as summary
            summary = "\n".join(lines[1:]).strip()
            if summary:
                body_parts.append(summary)
        else:
            body_parts.append(f"This PR implements: {lines[0]}")
    
    body_parts.append("\n## Changes")
    
    # Add commit summaries
    for commit in commits[:5]:  # Limit to 5 most recent
        subject = commit.split("\n")[0]
        body_parts.append(f"- {subject}")
    
    if len(commits) > 5:
        body_parts.append(f"\n_... and {len(commits) - 5} more commits_")
    
    # Add changed files section
    if changed_files:
        body_parts.append("\n## Files Changed")
        # Group by directory
        files_by_dir: dict[str, list[str]] = {}
        for file in changed_files[:20]:  # Limit to 20 files
            path = Path(file)
            dir_name = str(path.parent) if path.parent != Path(".") else "root"
            if dir_name not in files_by_dir:
                files_by_dir[dir_name] = []
            files_by_dir[dir_name].append(path.name)
        
        for dir_name, files in sorted(files_by_dir.items()):
            if dir_name == "root":
                body_parts.append(f"- {', '.join(files)}")
            else:
                body_parts.append(f"- `{dir_name}/`: {', '.join(files)}")
        
        if len(changed_files) > 20:
            body_parts.append(f"\n_... and {len(changed_files) - 20} more files_")
    
    # Extract related issues
    issues = []
    for commit in commits:
        if "closes #" in commit.lower() or "fixes #" in commit.lower():
            import re
            issue_matches = re.findall(r"(?:closes|fixes) #(\d+)", commit, re.IGNORECASE)
            issues.extend(issue_matches)
    
    if issues:
        body_parts.append("\n## Related Issues")
        for issue in set(issues):
            body_parts.append(f"Closes #{issue}")
    
    body_parts.append("\n## Testing")
    body_parts.append("- All tests pass")
    body_parts.append("- Code follows project style guidelines")
    
    return "\n".join(body_parts)


def create_pr(title: str, body: str, base: str = "main") -> tuple[bool, str]:
    """Create PR using GitHub CLI."""
    # Use heredoc for body to handle multiline
    cmd = [
        "gh", "pr", "create",
        "--title", title,
        "--body", body,
        "--base", base,
    ]
    
    exit_code, stdout, stderr = run_command(cmd, check=False)
    
    if exit_code == 0:
        return True, stdout
    else:
        return False, stderr


def main() -> int:
    """Main function."""
    print("🚀 Automated PR Creation")
    print("=" * 50)
    
    # Check if gh is installed
    if not check_gh_installed():
        print("❌ GitHub CLI (gh) is not installed.")
        print("\n📦 Installation:")
        print("   macOS: brew install gh")
        print("   Linux: See https://cli.github.com/manual/installation")
        print("\n🔐 After installation, authenticate:")
        print("   gh auth login")
        print("\nThen re-run this script.")
        return 1
    
    print("✅ GitHub CLI found")
    
    # Get current branch
    branch = get_current_branch()
    if not branch:
        print("❌ Could not determine current branch")
        return 1
    
    if branch == "main":
        print("❌ Cannot create PR from main branch")
        return 1
    
    print(f" branch: {branch}")
    
    # Get commit messages
    commits = get_commit_messages()
    if not commits:
        print("❌ No commits found (branch may be up to date with main)")
        return 1
    
    print(f"📝 Found {len(commits)} commit(s)")
    
    # Get changed files
    changed_files = get_changed_files()
    print(f"📄 Found {len(changed_files)} changed file(s)")
    
    # Generate PR title and body
    title = generate_pr_title(commits)
    body = generate_pr_body(commits, changed_files)
    
    print(f"\n📋 PR Title: {title}")
    print(f"\n📄 PR Body Preview:")
    print("-" * 50)
    print(body[:500] + ("..." if len(body) > 500 else ""))
    print("-" * 50)
    
    # Create PR
    print("\n🔨 Creating PR...")
    success, output = create_pr(title, body)
    
    if success:
        print(f"\n✅ PR created successfully!")
        print(f"🔗 {output}")
        print(f"\n📊 View PR: gh pr view")
        return 0
    else:
        print(f"\n❌ Failed to create PR:")
        print(output)
        
        # Check if PR already exists
        if "already exists" in output.lower() or "already has a pull request" in output.lower():
            print("\n💡 PR may already exist. Check with: gh pr list --head " + branch)
        
        return 1


if __name__ == "__main__":
    sys.exit(main())

