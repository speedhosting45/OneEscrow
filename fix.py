#!/usr/bin/env python3
"""
Syntax Fixer for main.py - Scans and fixes common syntax errors
"""
import re
import os
import sys

def fix_syntax_errors(file_path):
    """Fix common syntax errors in Python files"""
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    original_content = content
    fixes_applied = []
    
    print(f"🔍 Scanning {file_path} for syntax errors...")
    
    # Fix 1: Remove stray closing parentheses
    pattern = r'^\s*\)\s*$'
    matches = re.findall(pattern, content, re.MULTILINE)
    if matches:
        content = re.sub(pattern, '', content)
        fixes_applied.append(f"Removed {len(matches)} stray closing parentheses")
    
    # Fix 2: Fix unmatched parentheses in multiline strings
    # Look for multiline strings with mismatched quotes
    lines = content.split('\n')
    in_multiline_string = False
    quote_char = None
    for i, line in enumerate(lines):
        # Check if we're entering/exiting a multiline string
        if '"""' in line or "'''" in line:
            if not in_multiline_string:
                in_multiline_string = True
                quote_char = '"""' if '"""' in line else "'''"
            else:
                # Check if this is the closing quote
                if quote_char in line:
                    in_multiline_string = False
                    quote_char = None
        
        # If we find a stray ) while inside a multiline string, remove it
        if in_multiline_string and ')' in line:
            # Check if it's likely part of the string content
            if not re.search(r'[\w\)]', line.replace(')', '').strip()):
                lines[i] = line.replace(')', '')
                fixes_applied.append(f"Fixed stray parenthesis in multiline string at line {i+1}")
    
    content = '\n'.join(lines)
    
    # Fix 3: Fix trailing commas in function calls
    pattern = r',\s*\)'
    matches = re.findall(pattern, content)
    if matches:
        content = re.sub(pattern, ')', content)
        fixes_applied.append(f"Fixed {len(matches)} trailing commas in function calls")
    
    # Fix 4: Fix missing commas in lists/dicts
    # Look for lines ending with values but no comma before closing bracket
    pattern = r'([\w"\'])\s*\n\s*\]'
    if re.search(pattern, content):
        content = re.sub(pattern, r'\1,\n]', content)
        fixes_applied.append("Added missing comma in list")
    
    pattern = r'([\w"\'])\s*\n\s*\}'  
    if re.search(pattern, content):
        content = re.sub(pattern, r'\1,\n}', content)
        fixes_applied.append("Added missing comma in dict")
    
    # Fix 5: Fix mismatched quotes in strings
    # Single quotes inside double quotes
    pattern = r'""".*?\'\'\'.*?"""'
    if re.search(pattern, content, re.DOTALL):
        # Replace triple double quotes with triple single quotes
        content = re.sub(pattern, lambda m: m.group().replace('"""', "'''"), content)
        fixes_applied.append("Fixed mismatched triple quotes")
    
    # Fix 6: Remove extra blank lines at end of file
    content = content.rstrip() + '\n'
    
    # Fix 7: Fix indentation (common issue)
    lines = content.split('\n')
    fixed_lines = []
    indent_level = 0
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped:
            # Check for dedent
            if stripped.startswith('except') or stripped.startswith('else') or stripped.startswith('elif') or stripped.startswith('finally'):
                indent_level = max(0, indent_level - 1)
            
            # Check for class/method definitions
            if stripped.startswith('class ') or stripped.startswith('def ') or stripped.startswith('async def '):
                # Reset indent for new block
                indent_level = 0 if stripped.startswith('class ') else 1
            
            # Apply proper indentation
            expected_indent = '    ' * indent_level
            if not line.startswith(expected_indent) and line.strip():
                fixed_line = expected_indent + stripped
                if line != fixed_line:
                    fixes_applied.append(f"Fixed indentation at line {i+1}")
                    line = fixed_line
            
            # Check for indent increase
            if stripped.endswith(':'):
                indent_level += 1
    
    content = '\n'.join(lines)
    
    # Fix 8: Check for syntax errors by trying to compile
    try:
        compile(content, file_path, 'exec')
        print("✅ Syntax check passed!")
    except SyntaxError as e:
        print(f"⚠️ Syntax error found: {e}")
        print(f"   Line {e.lineno}: {e.text}")
        
        # Try to fix common syntax error patterns
        error_line = e.lineno - 1
        lines = content.split('\n')
        
        if e.msg == "unmatched ')'":
            # Remove the problematic parenthesis
            if error_line < len(lines):
                lines[error_line] = lines[error_line].replace(')', '', 1)
                fixes_applied.append(f"Removed unmatched parenthesis at line {e.lineno}")
        
        elif "EOL while scanning string literal" in e.msg:
            # Fix unclosed string
            if error_line < len(lines):
                lines[error_line] = lines[error_line] + '"'
                fixes_applied.append(f"Fixed unclosed string at line {e.lineno}")
        
        content = '\n'.join(lines)
    
    # Check if we made any changes
    if content != original_content:
        # Backup original file
        backup_path = file_path + '.backup'
        with open(backup_path, 'w') as f:
            f.write(original_content)
        print(f"📁 Backup saved to: {backup_path}")
        
        # Write fixed file
        with open(file_path, 'w') as f:
            f.write(content)
        
        print("✅ Applied fixes:")
        for fix in fixes_applied:
            print(f"   • {fix}")
        
        # Verify the fix worked
        try:
            compile(content, file_path, 'exec')
            print("✅ Final syntax check: PASSED")
            return True
        except SyntaxError as e:
            print(f"❌ Still has syntax error after fixes: {e}")
            print(f"   Line {e.lineno}: {e.text}")
            return False
    else:
        print("✅ No syntax errors found!")
        return True

def find_python_errors():
    """Find Python files with syntax errors in current directory"""
    print("🔍 Scanning for Python files with syntax errors...")
    
    python_files = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    problematic_files = []
    
    for py_file in python_files:
        try:
            with open(py_file, 'r') as f:
                content = f.read()
            compile(content, py_file, 'exec')
        except SyntaxError as e:
            problematic_files.append((py_file, e))
            print(f"❌ {py_file}: {e.msg} at line {e.lineno}")
    
    return problematic_files

def quick_fix_main_py():
    """Quick fix for common main.py issues"""
    if not os.path.exists('main.py'):
        print("❌ main.py not found in current directory")
        return False
    
    with open('main.py', 'r') as f:
        content = f.read()
    
    print("🔧 Applying quick fixes to main.py...")
    
    # Common fix: Remove stray closing parentheses at line 465
    lines = content.split('\n')
    
    if len(lines) > 464:
        line_465 = lines[464]
        if line_465.strip() == ')':
            print("⚠️ Found stray ')' at line 465 - removing")
            lines[464] = ''
    
    # Fix multiline string issues
    fixed_content = '\n'.join(lines)
    
    # Fix: Ensure proper string formatting in send_wallet_setup method
    pattern = r'message = f"""<b>✅ Participants Confirmed</b>'
    if re.search(pattern, fixed_content):
        print("⚠️ Found problematic multiline string - fixing...")
        # Replace with proper formatting
        fixed_content = re.sub(
            r'message = f"""<b>✅ Participants Confirmed</b>',
            r'message_text = f"""<b>✅ Participants Confirmed</b>',
            fixed_content
        )
    
    # Write fixed content
    with open('main.py.fixed', 'w') as f:
        f.write(fixed_content)
    
    print("✅ Created fixed version: main.py.fixed")
    print("📋 To use: cp main.py.fixed main.py")
    
    return True

def main():
    """Main function"""
    print("="*60)
    print("🔧 PYTHON SYNTAX FIXER")
    print("="*60)
    
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
    else:
        target_file = 'main.py'
    
    print(f"📄 Target file: {target_file}")
    print("-"*60)
    
    # Option 1: Quick fix
    if input("Run quick fix? (y/n): ").lower() == 'y':
        quick_fix_main_py()
    
    # Option 2: Full scan and fix
    if input("Run full syntax scan and fix? (y/n): ").lower() == 'y':
        if fix_syntax_errors(target_file):
            print("\n✅ Fix completed successfully!")
        else:
            print("\n❌ Fix failed!")
    
    # Option 3: Find all problematic files
    if input("Scan all Python files for errors? (y/n): ").lower() == 'y':
        problematic_files = find_python_errors()
        if problematic_files:
            print(f"\n⚠️ Found {len(problematic_files)} files with syntax errors")
            for file_path, error in problematic_files:
                print(f"   • {file_path}: {error.msg}")
        else:
            print("\n✅ No syntax errors found in any Python files!")
    
    print("\n" + "="*60)
    print("💡 Tips to avoid syntax errors:")
    print("   1. Use consistent indentation (4 spaces)")
    print("   2. Close all quotes, parentheses, and brackets")
    print("   3. Don't mix tabs and spaces")
    print("   4. Check for stray punctuation at line ends")
    print("   5. Use a code editor with syntax highlighting")
    print("="*60)

if __name__ == '__main__':
    main()
