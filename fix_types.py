import re
import glob

type_patterns = [
    r'->\s*Tuple\[[^:]+\]:',
    r'->\s*Optional\[[^:]+\]:',
    r'->\s*[A-Za-z0-9_]+:',
    r':\s*Optional\[([^\]]+)\]',
    r':\s*Tuple\[([^\]]+)\]',
    r':\s*yagmail\.SMTP',
    r':\s*list',
    r':\s*dict',
    r':\s*str',
    r':\s*int',
    r':\s*bool',
    r':\s*Any',
]

for filename in glob.glob("*.py"):
    if filename.startswith("scratch_") or filename == "fix_types.py" or filename == "app.py":
        continue
    with open(filename, "r", encoding="utf-8") as f:
        code = f.read()

    # Remove -> ReturnType:
    code = re.sub(r'\s*->\s*[a-zA-Z0-9_\[\],\.\s]+:', ':', code)
    
    # Remove args
    # find functions
    def replacer(match):
        arg_str = match.group(0)
        # remove anything after colon up to comma or parenthesis, except if it's default value '='
        # Actually easier: remove specific types
        for t in type_patterns:
            arg_str = re.sub(t, '', arg_str)
        # Fallback for remaining : type
        arg_str = re.sub(r':\s*[A-Za-z0-9_\[\],\.]+', '', arg_str)
        return arg_str
        
    code = re.sub(r'def\s+\w+\s*\((.*?)\)\s*:', replacer, code, flags=re.DOTALL)
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)

print("Tipos arreglados!")
