import sys, subprocess, json, base64

def eval_safari(js_code):
    """
    通过 Base64 + 立即执行函数安全求值，自动兼容 return 语句与任意表达式。
    """
    stripped = js_code.strip()
    if "return " in stripped and not (stripped.startswith("(() =>") or stripped.startswith("(function")):
        wrapped_code = f"(() => {{\n{stripped}\n}})()"
    else:
        wrapped_code = stripped
        
    b64 = base64.b64encode(wrapped_code.encode("utf-8")).decode("ascii")
    run_expr = f"(function(){{ try {{ var s = decodeURIComponent(escape(window.atob('{b64}'))); var r = eval(s); return r !== undefined ? String(r) : ''; }} catch(e) {{ return 'JS_ERR: ' + e.message; }} }})()"
    
    applescript = f'''
    tell application "Safari"
        set targetTab to missing value
        repeat with w in windows
            repeat with t in tabs of w
                if (URL of t as string) contains "smartedu.cn" then
                    set targetTab to t
                    exit repeat
                end if
            end repeat
            if targetTab is not missing value then exit repeat
        end repeat
        if targetTab is missing value then
            set targetTab to current tab of front window
        end if
        set res to do JavaScript "{run_expr}" in targetTab
        return res
    end tell
    '''
    proc = subprocess.run(["osascript", "-"], input=applescript, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"AppleScript error: {proc.stderr.strip()}")
    res = proc.stdout.strip()
    if res.startswith("JS_ERR:"):
        raise RuntimeError(res)
    return res

if __name__ == "__main__":
    if len(sys.argv) > 1:
        js = sys.argv[1]
    else:
        js = sys.stdin.read()
    print(eval_safari(js))
