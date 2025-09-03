#!/usr/bin/env python3
"""
Semantic Version Manager for Knowledge Ingestor

This script manages semantic versioning with alpha character increments.
Supports versions like: 1.0.7, 1.0.7.a, 1.0.7.b, ..., 1.0.7.z, then 1.0.8

Usage:
    python scripts/version_manager.py current
    python scripts/version_manager.py increment [major|minor|patch|alpha]
    python scripts/version_manager.py set <version>
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Tuple, Optional

class VersionManager:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.pyproject_path = project_root / "pyproject.toml"
        self.version_file = project_root / "VERSION"
        
    def get_current_version(self) -> str:
        """Get current version from VERSION file or pyproject.toml"""
        if self.version_file.exists():
            return self.version_file.read_text().strip()
        
        # Fallback to pyproject.toml
        if self.pyproject_path.exists():
            content = self.pyproject_path.read_text()
            match = re.search(r'version\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)
        
        return "0.1.0"
    
    def parse_version(self, version: str) -> Tuple[int, int, int, Optional[str]]:
        """Parse version string into components"""
        pattern = r"(\d+)\.(\d+)\.(\d+)(?:\.([a-z]))?$"
        match = re.match(pattern, version)
        
        if not match:
            raise ValueError(f"Invalid version format: {version}")
        
        major, minor, patch, alpha = match.groups()
        return int(major), int(minor), int(patch), alpha
    
    def format_version(self, major: int, minor: int, patch: int, alpha: Optional[str] = None) -> str:
        """Format version components into version string"""
        base = f"{major}.{minor}.{patch}"
        return f"{base}.{alpha}" if alpha else base
    
    def increment_version(self, increment_type: str) -> str:
        """Increment version based on type"""
        current = self.get_current_version()
        major, minor, patch, alpha = self.parse_version(current)
        
        if increment_type == "major":
            return self.format_version(major + 1, 0, 0)
        elif increment_type == "minor":
            return self.format_version(major, minor + 1, 0)
        elif increment_type == "patch":
            if alpha:
                # Complete the alpha series by removing alpha
                return self.format_version(major, minor, patch + 1)
            else:
                return self.format_version(major, minor, patch + 1)
        elif increment_type == "alpha":
            if alpha:
                # Increment alpha character
                if alpha == 'z':
                    # Roll over to next patch version
                    return self.format_version(major, minor, patch + 1)
                else:
                    next_alpha = chr(ord(alpha) + 1)
                    return self.format_version(major, minor, patch, next_alpha)
            else:
                # Start alpha series
                return self.format_version(major, minor, patch, 'a')
        else:
            raise ValueError(f"Invalid increment type: {increment_type}")
    
    def set_version(self, version: str) -> None:
        """Set version in all relevant files"""
        # Validate version format
        self.parse_version(version)
        
        # Update VERSION file
        self.version_file.write_text(f"{version}\n")
        
        # Update pyproject.toml if it exists
        if self.pyproject_path.exists():
            content = self.pyproject_path.read_text()
            updated_content = re.sub(
                r'(version\s*=\s*)"[^"]+"',
                f'\\1"{version}"',
                content
            )
            self.pyproject_path.write_text(updated_content)
        
        print(f"Version updated to: {version}")
    
    def create_git_tag(self, version: str) -> bool:
        """Create git tag for version"""
        import subprocess
        
        try:
            # Check if tag already exists
            result = subprocess.run(
                ["git", "tag", "-l", f"v{version}"],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )
            
            if result.stdout.strip():
                print(f"Tag v{version} already exists")
                return False
            
            # Create annotated tag
            subprocess.run(
                ["git", "tag", "-a", f"v{version}", "-m", f"Release v{version}"],
                check=True,
                cwd=self.project_root
            )
            
            print(f"Created git tag: v{version}")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to create git tag: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Semantic Version Manager")
    parser.add_argument("command", choices=["current", "increment", "set", "tag"])
    parser.add_argument("type_or_version", nargs="?", 
                       help="Increment type (major|minor|patch|alpha) or version string")
    parser.add_argument("--tag", action="store_true", 
                       help="Create git tag after setting version")
    
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent
    vm = VersionManager(project_root)
    
    try:
        if args.command == "current":
            print(vm.get_current_version())
        
        elif args.command == "increment":
            if not args.type_or_version:
                parser.error("increment command requires type (major|minor|patch|alpha)")
            
            new_version = vm.increment_version(args.type_or_version)
            vm.set_version(new_version)
            
            if args.tag:
                vm.create_git_tag(new_version)
        
        elif args.command == "set":
            if not args.type_or_version:
                parser.error("set command requires version string")
            
            vm.set_version(args.type_or_version)
            
            if args.tag:
                vm.create_git_tag(args.type_or_version)
        
        elif args.command == "tag":
            current_version = vm.get_current_version()
            vm.create_git_tag(current_version)
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()