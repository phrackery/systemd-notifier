# Contributing to systemd-notifier

Thank you for your interest in contributing to systemd-notifier! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)

## Code of Conduct

This project and everyone participating in it is governed by our commitment to:
- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Accept responsibility for mistakes

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Create a new branch for your feature or bug fix
4. Make your changes
5. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.7+
- D-Bus Python bindings
- curl
- systemd (for testing)

### Setup Script

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/systemd-notifier.git
cd systemd-notifier

# Install development dependencies
pip install -r requirements-dev.txt  # If we create one

# Run the notifier in test mode
./src/notifier.py --test-config
```

## How to Contribute

### Reporting Bugs

Before creating a bug report, please check if the issue already exists.

When reporting bugs, include:
- **OS and version** (e.g., Ubuntu 22.04)
- **systemd version** (`systemctl --version`)
- **Python version** (`python3 --version`)
- **Steps to reproduce**
- **Expected behavior**
- **Actual behavior**
- **Logs** (`journalctl --user -u system-notifier -n 100`)

### Suggesting Enhancements

Enhancement suggestions are welcome! Please:
- Use a clear, descriptive title
- Provide detailed description
- Explain why this enhancement would be useful
- List any alternative solutions you've considered

### Pull Requests

1. Update the README.md with details of changes if applicable
2. Update INSTALL.md if installation steps change
3. Ensure your code follows the coding standards
4. Include appropriate comments
5. Test your changes thoroughly

## Coding Standards

### Python Code

- Follow PEP 8 style guide
- Use type hints where appropriate
- Maximum line length: 100 characters
- Use docstrings for functions and classes

Example:
```python
def send_notification(event: EventInfo) -> bool:
    """Send notification to Telegram.
    
    Args:
        event: Event information containing type, hostname, timestamp
        
    Returns:
        True if message was sent successfully, False otherwise
    """
    pass
```

### Bash Code

- Use `#!/usr/bin/env bash`
- Use `set -euo pipefail`
- Quote all variables
- Use meaningful variable names

Example:
```bash
#!/usr/bin/env bash
set -euo pipefail

send_message() {
    local message="$1"
    local max_retries="${2:-3}"
    # ...
}
```

### Configuration Files

- Use clear, descriptive names
- Add comments explaining each option
- Provide sensible defaults

## Testing

### Manual Testing Checklist

Before submitting a PR, test:
- [ ] Installation works on clean system
- [ ] Configuration loads correctly
- [ ] Lock notification fires
- [ ] Sleep notification fires
- [ ] Shutdown notification fires
- [ ] Telegram message is received
- [ ] Service starts/stops correctly
- [ ] Logs are informative

### Testing Commands

```bash
# Test configuration loading
python3 -c "from src.notifier import ConfigManager; c = ConfigManager(); print('OK')"

# Test Telegram script
export TELEGRAM_BOT_TOKEN="test"
export TELEGRAM_CHAT_ID="test"
./src/telegram.sh "Test message" 2>&1 || true

# Test D-Bus connection
python3 -c "from gi.repository import Gio, GLib; print('D-Bus OK')"
```

## Commit Messages

Use clear, meaningful commit messages:

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit first line to 72 characters
- Reference issues and PRs where appropriate

Good examples:
```
Add support for custom notification sounds

Fix race condition in sleep detection

Update README with Fedora installation steps

Refactor telegram sender to use requests library
```

## Pull Request Process

1. **Update documentation** if needed
2. **Describe your changes** clearly in the PR description
3. **Link related issues** using keywords (Fixes #123)
4. **Wait for review** - be patient, maintainers are volunteers
5. **Address feedback** - make requested changes
6. **Squash commits** if requested

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Refactoring
- [ ] Other: ___

## Testing
- [ ] Tested on Ubuntu
- [ ] Tested on Arch Linux
- [ ] All existing tests pass

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex code
- [ ] Documentation updated
- [ ] No new warnings introduced
```

## Areas for Contribution

### High Priority

- [ ] Windows support (WMI events)
- [ ] macOS support (NSWorkspace)
- [ ] Unit tests
- [ ] Integration tests

### Medium Priority

- [ ] Discord/Slack backends
- [ ] GUI configuration tool
- [ ] Better error recovery
- [ ] Log rotation

### Low Priority

- [ ] Metrics/monitoring
- [ ] Performance optimizations
- [ ] Additional notification channels

## Questions?

Feel free to:
- Open an issue for questions
- Join discussions
- Contact maintainers

Thank you for contributing! 🎉
