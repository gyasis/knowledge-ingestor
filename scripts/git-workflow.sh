#!/bin/bash

# Git Workflow Helper Script for Knowledge Ingestor
# This script provides common Git workflow operations with proper security checks

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Security check function
security_check() {
    echo -e "${YELLOW}🔒 SECURITY CHECK: Verifying no sensitive files are staged...${NC}"
    
    # Check for sensitive files
    SENSITIVE_FILES=".specstory/ .cursor/ claude.md cursor.md CLAUDE.md .env.local"
    
    for file in $SENSITIVE_FILES; do
        if git diff --cached --name-only | grep -q "$file"; then
            echo -e "${RED}❌ SECURITY VIOLATION: Sensitive file '$file' is staged!${NC}"
            echo -e "${RED}   Removing from staging area...${NC}"
            git reset HEAD "$file" 2>/dev/null || true
        fi
    done
    
    # Check for any .md files in root except README.md
    ROOT_MD_FILES=$(git diff --cached --name-only | grep "^[^/]*\.md$" | grep -v "README.md" || true)
    if [ -n "$ROOT_MD_FILES" ]; then
        echo -e "${YELLOW}⚠️  WARNING: Root .md files detected (excluding README.md):${NC}"
        echo "$ROOT_MD_FILES"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${RED}❌ Aborting commit${NC}"
            exit 1
        fi
    fi
    
    echo -e "${GREEN}✅ Security check passed${NC}"
}

# Function to create a new feature branch
create_feature_branch() {
    local branch_name="$1"
    
    if [ -z "$branch_name" ]; then
        echo -e "${RED}❌ Branch name required${NC}"
        echo "Usage: $0 feature <branch-name>"
        exit 1
    fi
    
    # Ensure we're on master or develop
    current_branch=$(git branch --show-current)
    if [[ "$current_branch" != "master" && "$current_branch" != "develop" ]]; then
        echo -e "${YELLOW}⚠️  Not on master or develop branch. Switching to master...${NC}"
        git checkout master
    fi
    
    # Create and switch to feature branch
    echo -e "${BLUE}🌿 Creating feature branch: feature/$branch_name${NC}"
    git checkout -b "feature/$branch_name"
    
    # Increment to alpha version
    echo -e "${BLUE}📊 Incrementing to alpha version...${NC}"
    python scripts/version_manager.py increment alpha
    
    echo -e "${GREEN}✅ Feature branch 'feature/$branch_name' created and ready for development${NC}"
}

# Function to create a fix branch
create_fix_branch() {
    local branch_name="$1"
    
    if [ -z "$branch_name" ]; then
        echo -e "${RED}❌ Branch name required${NC}"
        echo "Usage: $0 fix <branch-name>"
        exit 1
    fi
    
    # Ensure we're on master
    current_branch=$(git branch --show-current)
    if [ "$current_branch" != "master" ]; then
        echo -e "${YELLOW}⚠️  Not on master branch. Switching to master...${NC}"
        git checkout master
    fi
    
    # Create and switch to fix branch
    echo -e "${BLUE}🔧 Creating fix branch: fix/$branch_name${NC}"
    git checkout -b "fix/$branch_name"
    
    # Increment to alpha version
    echo -e "${BLUE}📊 Incrementing to alpha version...${NC}"
    python scripts/version_manager.py increment alpha
    
    echo -e "${GREEN}✅ Fix branch 'fix/$branch_name' created and ready for development${NC}"
}

# Function to commit with security checks
secure_commit() {
    local message="$1"
    
    if [ -z "$message" ]; then
        echo -e "${RED}❌ Commit message required${NC}"
        echo "Usage: $0 commit \"<commit-message>\""
        exit 1
    fi
    
    # Run security check
    security_check
    
    # Check if there are staged changes
    if git diff --cached --quiet; then
        echo -e "${YELLOW}⚠️  No changes staged for commit${NC}"
        exit 1
    fi
    
    # Show what will be committed
    echo -e "${BLUE}📋 Files to be committed:${NC}"
    git diff --cached --name-only
    
    # Confirm commit
    read -p "Proceed with commit? (Y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo -e "${YELLOW}❌ Commit cancelled${NC}"
        exit 1
    fi
    
    # Commit with proper format
    git commit -m "$message

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"
    
    echo -e "${GREEN}✅ Commit completed successfully${NC}"
}

# Function to increment version
increment_version() {
    local type="$1"
    
    if [ -z "$type" ]; then
        echo -e "${RED}❌ Version increment type required${NC}"
        echo "Usage: $0 version <alpha|patch|minor|major>"
        exit 1
    fi
    
    current_version=$(python scripts/version_manager.py current)
    echo -e "${BLUE}📊 Current version: $current_version${NC}"
    
    new_version=$(python scripts/version_manager.py increment "$type")
    echo -e "${GREEN}✅ Version incremented to: $new_version${NC}"
    
    # Stage version files
    git add VERSION pyproject.toml
    
    # Commit version change
    secure_commit "chore: bump version to $new_version"
}

# Function to merge feature/fix branch
merge_branch() {
    local branch_type="$1"
    
    current_branch=$(git branch --show-current)
    
    # Validate branch type
    if [[ ! "$current_branch" =~ ^(feature|fix)/ ]]; then
        echo -e "${RED}❌ Not on a feature or fix branch${NC}"
        exit 1
    fi
    
    # Extract branch info
    branch_name=$(echo "$current_branch" | cut -d'/' -f2-)
    
    echo -e "${BLUE}🔄 Merging $current_branch into master...${NC}"
    
    # Switch to master
    git checkout master
    
    # Merge feature branch
    git merge --no-ff "$current_branch" -m "Merge $current_branch

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"
    
    # Increment to next semantic version (complete the alpha series)
    echo -e "${BLUE}📊 Completing version increment...${NC}"
    python scripts/version_manager.py increment patch
    
    # Stage and commit version completion
    git add VERSION pyproject.toml
    new_version=$(python scripts/version_manager.py current)
    git commit -m "chore: complete version increment to $new_version

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"
    
    # Ask about branch cleanup
    read -p "Delete merged branch '$current_branch'? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        git branch -d "$current_branch"
        echo -e "${GREEN}✅ Branch '$current_branch' deleted${NC}"
    fi
    
    echo -e "${GREEN}✅ Merge completed successfully${NC}"
}

# Function to show workflow status
show_status() {
    echo -e "${BLUE}📊 Knowledge Ingestor Git Workflow Status${NC}"
    echo "=================================="
    echo
    
    # Current branch and version
    current_branch=$(git branch --show-current)
    current_version=$(python scripts/version_manager.py current)
    
    echo -e "Current Branch: ${GREEN}$current_branch${NC}"
    echo -e "Current Version: ${GREEN}$current_version${NC}"
    echo
    
    # Git status
    echo -e "${BLUE}Git Status:${NC}"
    git status --short
    echo
    
    # Recent commits
    echo -e "${BLUE}Recent Commits:${NC}"
    git log --oneline -5
    echo
    
    # Branches
    echo -e "${BLUE}Local Branches:${NC}"
    git branch
}

# Function to setup pre-commit hooks
setup_hooks() {
    echo -e "${BLUE}🔗 Setting up pre-commit hooks...${NC}"
    
    # Install pre-commit if not already installed
    if ! command -v pre-commit &> /dev/null; then
        echo -e "${YELLOW}⚠️  Installing pre-commit...${NC}"
        pip install pre-commit
    fi
    
    # Install hooks
    pre-commit install
    
    # Run hooks on all files
    echo -e "${BLUE}🔍 Running hooks on all files...${NC}"
    pre-commit run --all-files
    
    echo -e "${GREEN}✅ Pre-commit hooks installed and tested${NC}"
}

# Main script logic
case "$1" in
    "feature")
        create_feature_branch "$2"
        ;;
    "fix")
        create_fix_branch "$2"
        ;;
    "commit")
        secure_commit "$2"
        ;;
    "version")
        increment_version "$2"
        ;;
    "merge")
        merge_branch
        ;;
    "status")
        show_status
        ;;
    "hooks")
        setup_hooks
        ;;
    "help"|"--help"|"-h"|"")
        echo -e "${BLUE}Knowledge Ingestor Git Workflow Helper${NC}"
        echo "======================================"
        echo
        echo "Usage: $0 <command> [arguments]"
        echo
        echo "Commands:"
        echo -e "  ${GREEN}feature <name>${NC}     Create a new feature branch"
        echo -e "  ${GREEN}fix <name>${NC}         Create a new fix branch"  
        echo -e "  ${GREEN}commit <message>${NC}   Secure commit with security checks"
        echo -e "  ${GREEN}version <type>${NC}     Increment version (alpha|patch|minor|major)"
        echo -e "  ${GREEN}merge${NC}              Merge current feature/fix branch to master"
        echo -e "  ${GREEN}status${NC}             Show workflow status"
        echo -e "  ${GREEN}hooks${NC}              Setup pre-commit hooks"
        echo -e "  ${GREEN}help${NC}               Show this help message"
        echo
        echo "Examples:"
        echo "  $0 feature user-authentication"
        echo "  $0 commit \"feat(auth): add OAuth integration\""
        echo "  $0 version alpha"
        echo "  $0 merge"
        echo
        echo -e "${YELLOW}Security Notes:${NC}"
        echo "- Automatically excludes sensitive files (.specstory/, claude.md, etc.)"
        echo "- Warns about root .md files (except README.md)"
        echo "- Never use 'git add .' - always use selective staging"
        echo "- All commits include Claude Code attribution"
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $1${NC}"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac