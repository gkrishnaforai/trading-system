# Docker Build-Time Syntax Checking

## Overview

Python syntax errors are now caught during Docker image builds, preventing broken images from being created.

## Implementation

### 1. Dockerfile Syntax Checks

Both `streamlit-app/Dockerfile` and `python-worker/Dockerfile` now include syntax checking steps:

**Streamlit Dockerfile:**
```dockerfile
# Check Python syntax before finalizing image
RUN python3 -c "import ast, sys, glob; [ast.parse(open(f).read()) for f in glob.glob('*.py') + glob.glob('pages/*.py')]" || (echo "❌ Python syntax errors found! Fix before building." && exit 1)
```

**Python Worker Dockerfile:**
```dockerfile
# Check Python syntax before finalizing image
RUN python3 -c "import ast, os; [ast.parse(open(os.path.join(root, f)).read()) for root, dirs, files in os.walk('/app') for f in files if f.endswith('.py')]" || (echo "❌ Python syntax errors found! Fix before building." && exit 1)
```

### 2. Pre-Build Script

A standalone script is available for checking syntax before building:

```bash
./scripts/check_python_syntax.sh [directory]
```

**Features:**
- Checks all Python files recursively
- Uses `ast.parse()` (doesn't write to disk, no permission issues)
- Color-coded output
- Summary statistics
- Exit code 1 on errors (useful for CI/CD)

**Example:**
```bash
# Check all Python files
./scripts/check_python_syntax.sh

# Check specific directory
./scripts/check_python_syntax.sh streamlit-app/
```

## Benefits

1. **Fail Fast**: Syntax errors are caught during build, not at runtime
2. **CI/CD Integration**: Builds fail immediately if syntax errors exist
3. **Developer Feedback**: Clear error messages point to problematic files
4. **No Runtime Impact**: Syntax checking happens at build time only

## How It Works

The syntax check uses Python's `ast.parse()` module, which:
- Parses Python code into an Abstract Syntax Tree
- Validates syntax without executing code
- Doesn't require write permissions (unlike `py_compile`)
- Provides clear error messages with line numbers

## Example Error Output

```
❌ streamlit-app/testbed.py
  File "testbed.py", line 1480
    st.subheader("Calculation Results")
    ^
IndentationError: expected an indented block after 'if' statement on line 1479
```

## Integration with CI/CD

Add to your CI/CD pipeline:

```yaml
# Example GitHub Actions
- name: Check Python Syntax
  run: ./scripts/check_python_syntax.sh

# Or check specific directories
- name: Check Streamlit Syntax
  run: ./scripts/check_python_syntax.sh streamlit-app/
```

## Troubleshooting

### Permission Errors

If you see permission errors with `py_compile`, the script now uses `ast.parse()` which doesn't write to disk and avoids permission issues.

### False Positives

If a file has valid syntax but fails the check:
1. Verify the file encoding (should be UTF-8)
2. Check for hidden characters
3. Ensure proper line endings (Unix-style `\n`)

## Related Files

- `streamlit-app/Dockerfile` - Streamlit container with syntax check
- `python-worker/Dockerfile` - Python worker container with syntax check
- `scripts/check_python_syntax.sh` - Standalone syntax checker script

