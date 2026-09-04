import sys, subprocess, json

def applescript_quote(s):
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s}"'

def eval_safari(js_code, url_pattern="basic.smartedu.cn"):
    """
    在 Safari 中查找 URL 包含 url_pattern 的标签页并执行 JavaScript 代码。
    若找不到特定 Tab，则在当前激活 Tab 执行。
    """
    quoted_js = applescript_quote(js_code)
    applescript = f'''
    tell application "Safari"
        set targetTab to null
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t contains "{url_pattern}" and URL of t contains "prepare" then
                    set targetTab to t
                    exit repeat
                end if
            end repeat
            if targetTab is not null then exit repeat
        end repeat
        
        if targetTab is null then
            set targetTab to current tab of front window
        end if
        
        do JavaScript {quoted_js} in targetTab
    end tell
    '''
    proc = subprocess.run(["osascript", "-"], input=applescript, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"AppleScript error: {proc.stderr.strip()}")
    return proc.stdout.strip()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        js = sys.argv[1]
    else:
        js = sys.stdin.read()
    print(eval_safari(js))
