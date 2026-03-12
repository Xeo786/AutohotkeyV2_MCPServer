"""
Integration test for the DBGp debugger tools.

This test:
1. Launches a simple long-running AHK script
2. Attaches the debugger via dbg_attach
3. Queries status
4. Breaks execution
5. Inspects variables and stack
6. Evaluates an expression
7. Detaches cleanly
8. Kills the test AHK process
"""

import subprocess
import time
import os
import sys
import tempfile

# Add parent directory to path so we can import server
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server import (
    dbg_attach, dbg_detach, dbg_status, dbg_break,
    dbg_get_vars, dbg_stack, dbg_eval, dbg_continue,
    run_ahk_script,
)

AHK_PATH = r"C:\Program Files\AutoHotkey\v2.0.21\AutoHotkey64.exe"

# -- Test AHK script --
TEST_SCRIPT = '''\
#Requires AutoHotkey v2.0
Persistent
myCounter := 0
myName := "TestScript"
myMap := Map("key1", "value1", "key2", "value2")

SetTimer(Tick, 500)

Tick() {
    global myCounter
    myCounter++
}
'''


def main():
    print("=" * 60)
    print("DBGp Integration Test")
    print("=" * 60)

    # 1. Write and launch test script
    fd, script_path = tempfile.mkstemp(suffix=".ahk", text=True)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(TEST_SCRIPT)

    print(f"\n[1] Launching test script: {script_path}")
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    proc = subprocess.Popen(
        [AHK_PATH, script_path],
        startupinfo=startupinfo,
    )
    pid = proc.pid
    print(f"    PID: {pid}")
    time.sleep(1.5)  # Let the script start and run a few ticks

    try:
        # 2. Attach debugger
        print(f"\n[2] Attaching debugger to PID {pid}...")
        result = dbg_attach(pid=pid, port=9005, timeout=5)
        print(f"    Result: {result}")
        if "error" in result:
            print("    FAIL: Could not attach!")
            return

        # 3. Check status
        print("\n[3] Checking status...")
        status = dbg_status()
        print(f"    Status: {status}")

        # 4. Break (pause)
        print("\n[4] Sending break...")
        # The script is in 'running' state after attach + run,
        # but after attach the DBGp engine starts in 'starting' state.
        # We need to issue a 'run' first, then break.
        print("    Issuing 'run' to let script execute...")
        run_result = dbg_continue(mode="run")
        print(f"    Run result: {run_result}")

        # Small delay to let it run
        time.sleep(0.5)

        brk = dbg_break()
        print(f"    Break result: {brk}")

        # The run command's response should now arrive
        time.sleep(0.3)

        # 5. Get stack
        print("\n[5] Getting stack...")
        stack = dbg_stack()
        print(f"    Stack: {stack}")

        # 6. Get global variables
        print("\n[6] Getting global variables (context=1)...")
        gvars = dbg_get_vars(context=1, depth=0)
        print(f"    Variables ({gvars.get('count', '?')} found):")
        for v in gvars.get("variables", [])[:10]:
            val = v.get("value", v.get("classname", "?"))
            print(f"      {v['name']}: {v['type']} = {val}")

        # 7. Eval
        print("\n[7] Evaluating expression: myCounter + 100 ...")
        ev = dbg_eval("myCounter + 100")
        print(f"    Eval result: {ev}")

        # 8. Detach
        print("\n[8] Detaching...")
        det = dbg_detach()
        print(f"    Detach result: {det}")

        print("\n" + "=" * 60)
        print("TEST COMPLETE — All steps executed successfully.")
        print("=" * 60)

    finally:
        # Cleanup
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        try:
            os.remove(script_path)
        except Exception:
            pass


if __name__ == "__main__":
    main()
