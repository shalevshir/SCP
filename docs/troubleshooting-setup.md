# Troubleshooting Setup Issues

## Poetry Installation Error: "cannot create venvs without using symlinks"

This error occurs when using the system Python 3.9 from CommandLineTools on macOS. Here are solutions:

### Solution 1: Use uv (Recommended - Easiest)

`uv` is a fast Python package installer that doesn't require Python 3.11+ to install:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH (add to ~/.zshrc if needed)
export PATH="$HOME/.cargo/bin:$PATH"

# Install dependencies and create venv
cd /Users/shalev/Code/SCP
uv sync

# Run tests
uv run pytest
```

### Solution 2: Install Python 3.11+ via Homebrew

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.11
brew install python@3.11

# Use Python 3.11 with Poetry
poetry env use python3.11
poetry install --no-root
poetry run pytest
```

### Solution 3: Install Poetry with pipx

```bash
# Install pipx first
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install Poetry via pipx
pipx install poetry

# Then use Poetry
cd /Users/shalev/Code/SCP
poetry install --no-root
poetry run pytest
```

### Solution 4: Use pyenv to Manage Python Versions

```bash
# Install pyenv
brew install pyenv

# Install Python 3.11
pyenv install 3.11.9

# Set local Python version
cd /Users/shalev/Code/SCP
pyenv local 3.11.9

# Now Poetry will use Python 3.11
poetry install --no-root
poetry run pytest
```

### Solution 5: Manual Virtual Environment (Quick Test)

If you just want to test quickly, you can create a venv manually:

```bash
# Create venv (if your Python supports it)
python3 -m venv .venv --symlinks

# Or without symlinks (if above fails)
python3 -m venv .venv --without-pip

# Activate
source .venv/bin/activate

# Install pip manually if needed
curl https://bootstrap.pypa.io/get-pip.py | python3

# Install dependencies
pip install pytest pytest-xdist pyyaml pydantic

# Run tests
pytest
```

**Note:** This uses Python 3.9, but the project requires 3.11+. Some features may not work correctly.

## Recommended Approach

**For this project, I recommend Solution 1 (uv)** because:
- Fastest to set up
- Doesn't require Python 3.11+ to install
- Automatically manages Python versions
- Works well with the project's requirements

## Verify Installation

After setup, verify everything works:

```bash
# Check Python version (should be 3.11+)
python --version

# Check dependencies
pytest --version
python -c "import pydantic; print(pydantic.__version__)"

# Run tests
pytest -v
```

