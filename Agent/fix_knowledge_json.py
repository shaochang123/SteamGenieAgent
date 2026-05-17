import json
import os
import sys
from pathlib import Path


def fix_json_string(text: str) -> str:
    """Escape unescaped double quotes and control characters inside JSON string values."""
    result: list[str] = []
    i = 0
    in_string = False

    while i < len(text):
        c = text[i]

        if c == '"' and not in_string:
            result.append(c)
            in_string = True
            i += 1
            continue

        if in_string:
            if c == '\n':
                result.append('\\n')
                i += 1
                continue
            if c == '\r':
                result.append('\\r')
                i += 1
                continue
            if c == '\t':
                result.append('\\t')
                i += 1
                continue

        if c == '"' and in_string:
            j = i + 1
            while j < len(text) and text[j] in ' \t\n\r':
                j += 1
            next_char = text[j] if j < len(text) else ''

            if next_char in (',', '}', ':'):
                result.append(c)
                in_string = False
            else:
                result.append('\\"')
            i += 1
            continue

        if c == '\\' and in_string:
            result.append(c)
            i += 1
            if i < len(text):
                result.append(text[i])
                i += 1
            continue

        result.append(c)
        i += 1

    return ''.join(result)


def fix_json_file(filepath: str) -> bool:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        json.loads(content)
        return False  # already valid
    except json.JSONDecodeError:
        pass

    fixed = fix_json_string(content)

    try:
        json.loads(fixed)
    except json.JSONDecodeError as e:
        print(f"  [ERROR] {os.path.basename(filepath)}: still invalid after fix — {e}")
        return False

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(fixed)
    return True


def main():
    knowledge_dir = Path(__file__).parent / 'Knowledge'
    if not knowledge_dir.is_dir():
        print(f"Knowledge directory not found: {knowledge_dir}")
        sys.exit(1)

    json_files = list(knowledge_dir.glob('*.json'))
    if not json_files:
        print("No JSON files found in Knowledge directory.")
        return

    fixed_count = 0
    for fp in json_files:
        print(f"Checking: {fp.name} ... ", end='')
        try:
            if fix_json_file(str(fp)):
                print("FIXED")
                fixed_count += 1
            else:
                print("OK")
        except Exception as e:
            print(f"ERROR — {e}")

    print(f"\nDone. Fixed {fixed_count} file(s).")


if __name__ == '__main__':
    main()
