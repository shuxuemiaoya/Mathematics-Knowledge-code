import sys, subprocess, json, base64

def eval_safari(js_code):
    """
    通过 Base64 + 立即执行函数安全求值，自动兼容 return 语句与任意表达式。
    """
    # 如果代码包含 return 且不在函数内，将其包装在立即执行匿名函数中
    # 如果代码包含 return 且未被立即执行函数包裹，包裹为立即执行匿名函数
    stripped = js_code.strip()
    if "return " in stripped and not (stripped.startswith("(() =>") or stripped.startswith("(function")):
        wrapped_code = f"(() => {{\n{stripped}\n}})()"
    else:
        wrapped_code = stripped
        
    b64 = base64.b64encode(wrapped_code.encode("utf-8")).decode("ascii")
    run_expr = f"(function(){{ try {{ var s = decodeURIComponent(escape(window.atob('{b64}'))); var r = eval(s); return r !== undefined ? String(r) : ''; }} catch(e) {{ return 'JS_ERR: ' + e.message; }} }})()"
    
    applescript = f'''
    tell application "Safari"
        set targetTab to current tab of front window
        repeat with t in tabs of front window
            if URL of t contains "smartedu.cn" then
                set targetTab to t
                exit repeat
            end if
        end repeat
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
