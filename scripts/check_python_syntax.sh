#!/bin/bash
# Python Syntax Checker
# Checks all Python files for syntax errors before Docker build
# Usage: ./scripts/check_python_syntax.sh [directory]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default directory to check
CHECK_DIR="${1:-.}"

echo -e "${YELLOW}🔍 Checking Python syntax in ${CHECK_DIR}...${NC}"

# Find all Python files
PYTHON_FILES=$(find "${CHECK_DIR}" -type f -name "*.py" ! -path "*/venv/*" ! -path "*/__pycache__/*" ! -path "*/.git/*" ! -path "*/node_modules/*")

if [ -z "$PYTHON_FILES" ]; then
    echo -e "${YELLOW}⚠️  No Python files found in ${CHECK_DIR}${NC}"
    exit 0
fi

ERRORS=0
CHECKED=0

# Check each Python file using ast.parse (doesn't write to disk)
for file in $PYTHON_FILES; do
    CHECKED=$((CHECKED + 1))
    
    # Use ast.parse() to check syntax (doesn't require write permissions)
    if python3 -c "import ast; ast.parse(open('$file').read())" 2>&1; then
        echo -e "${GREEN}✅ ${file}${NC}"
    else
        echo -e "${RED}❌ ${file}${NC}"
        ERRORS=$((ERRORS + 1))
        # Show the actual error
        python3 -c "import ast; ast.parse(open('$file').read())" 2>&1 || true
    fi
done

echo ""
echo -e "${YELLOW}📊 Summary:${NC}"
echo -e "   Files checked: ${CHECKED}"
echo -e "   Errors found: ${ERRORS}"

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}❌ Syntax check failed! Please fix the errors above.${NC}"
    exit 1
else
    echo -e "${GREEN}✅ All Python files passed syntax check!${NC}"
    exit 0
fi
