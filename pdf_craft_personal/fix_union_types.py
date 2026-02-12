#!/usr/bin/env python3
"""
Script to fix Python 3.10+ union type syntax (|) to Python 3.9 compatible syntax
"""
import os
import re
import glob

def fix_file(filepath):
    """Fix union types in a single file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Fix patterns like "Type | None" -> "Optional[Type]"
    content = re.sub(r'(\w+(?:\[[^\]]+\])?)\s*\|\s*None', r'Optional[\1]', content)
    
    # Fix patterns like "Type1 | Type2" -> "Union[Type1, Type2]"
    content = re.sub(r'(\w+(?:\[[^\]]+\])?)\s*\|\s*(\w+(?:\[[^\]]+\])?)', r'Union[\1, \2]', content)
    
    # Add imports if needed
    if content != original_content:
        if 'Optional[' in content and 'from typing import' in content:
            if 'Optional' not in content.split('from typing import')[1].split('\n')[0]:
                content = re.sub(
                    r'(from typing import [^)\n]+)', 
                    r'\1, Optional', 
                    content
                )
        
        if 'Union[' in content and 'from typing import' in content:
            if 'Union' not in content.split('from typing import')[1].split('\n')[0]:
                content = re.sub(
                    r'(from typing import [^)\n]+)', 
                    r'\1, Union', 
                    content
                )
        
        # Add typing import if not exists
        if ('Optional[' in content or 'Union[' in content) and 'from typing import' not in content:
            imports_to_add = []
            if 'Optional[' in content:
                imports_to_add.append('Optional')
            if 'Union[' in content:
                imports_to_add.append('Union')
            
            content = f"from typing import {', '.join(imports_to_add)}\n" + content
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed: {filepath}")
        return True
    return False

def main():
    """Fix all Python files in the project"""
    fixed_count = 0
    
    # Find all Python files
    for filepath in glob.glob('pdf_craft/**/*.py', recursive=True):
        if fix_file(filepath):
            fixed_count += 1
    
    print(f"Fixed {fixed_count} files")

if __name__ == '__main__':
    main()