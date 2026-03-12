# AutoHotkey v2 MCP Server

**Created by [Xeo786](https://github.com/Xeo786)**

## What is it?
This is a custom **Model Context Protocol (MCP)** server built in Python, designed specifically to bridge the gap between AI coding assistants and the AutoHotkey v2 ecosystem on Windows. 

MCP is an open standard that enables AI models to connect securely to local data sources and tools. This server exposes powerful, specialized tools to the AI, granting it the context, execution, and **live debugging** capabilities needed to write perfect AHK scripts.

## Why was it created?
AutoHotkey v2 introduced strict object-oriented syntax, removing graceful failures and silent errors that existed in v1. When an AI tries to write AHK code blindly, it often:
1. Mixes up v1 and v2 syntax.
2. Cannot tell if the target window title or class is correct.
3. Cannot verify if the script even launches without crashing.
4. Doesn't know what custom libraries the user already has installed.
5. **Cannot debug running scripts** to diagnose issues.

This server solves **all** of these problems by giving the AI eyes (inspect active window), knowledge (search library), hands (validate and run), and now a **full debugger** (DBGp protocol integration).

---

## How does it help the AI? (Features)

The server exposes tools in two categories:

### Core Tools

#### 1. `validate_ahk_syntax`
- **What it does:** Runs external AHK code through AutoHotkey's `/Validate` switch, sending syntax errors to `/ErrorStdOut`.
- **How it helps:** The AI can verify that the code it just wrote is syntactically sound, catching missing braces, undefined variables, or v1 legacy commands *before* handing the script to the user.

#### 2. `run_ahk_script`
- **What it does:** Executes a temporary script and forcefully captures standard output (`FileAppend(text, "*")`) and runtime errors, strictly enforcing a timeout (e.g., 3 seconds) to prevent infinite loops.
- **How it helps:** The AI can test logical behavior (e.g., "Does this Regex expression actually match correctly in AHK?"). Fast feedback loops mean fewer broken scripts.

#### 3. `inspect_active_window`
- **What it does:** Runs a tiny script returning the Title, Class (`ahk_class`), and Executable (`ahk_exe`) of whatever window the user currently has focused.
- **How it helps:** Finding correct window hooks is tedious. The user can just focus an app, ask the AI to "write a script for my active window," and the AI can pull the exact selectors needed for `WinActivate` or `ControlSend`.

#### 4. `search_global_library`
- **What it does:** Performs a text search through the user's master AHK library folder.
- **How it helps:** Instead of reinventing the wheel (like creating a new WebSocket class), the AI can search the user's local drive, read the existing custom wrappers, and write code that utilizes the user's preferred ecosystem. 

#### 5. `configure_paths`
- **What it does:** Sets and persists the `AHK_PATH` and `GLOBAL_LIB_PATH` to the user's `AppData`.
- **New Feature:** Supports `use_dialog=True` to pop up native Windows file/directory selection dialogs on the host machine for easy setup.
- **How it helps:** Allows the server to remain portable and tool-neutral, letting the user (or AI) configure the exact binaries and libraries to use without editing the source code.

---

### DBGp Live Debugger Tools

These tools allow the AI to **attach to and debug running AutoHotkey scripts** in real-time using the [DBGp protocol](https://xdebug.org/docs/dbgp). This is the same protocol used by SciTE4AutoHotkey and VS Code debug adapters.

#### Connection Management
| Tool | Description |
|---|---|
| `dbg_attach(pid, port?, timeout?)` | Attach to a running AHK script by PID. Starts a TCP listener and sends `AHK_ATTACH_DEBUGGER` to trigger a debug connection. |
| `dbg_detach()` | Detach from the debug session, letting the script continue normally. |
| `dbg_status()` | Get the current debugger state (`break`, `running`, `stopped`, etc.). |

#### Execution Control
| Tool | Description |
|---|---|
| `dbg_break()` | Pause execution of a running script. |
| `dbg_continue(mode)` | Resume execution: `run`, `step_into`, `step_over`, or `step_out`. |

#### Inspection & Evaluation  
| Tool | Description |
|---|---|
| `dbg_stack()` | Get the current call stack (file, line, function). |
| `dbg_get_vars(context, depth)` | Get all variables in a context (`0`=Local, `1`=Global) at a stack depth. Filters out AHK built-in classes automatically. |
| `dbg_get_var(name, context, depth)` | Get a single variable by name. |
| `dbg_set_var(name, value)` | Set a variable's value at runtime. |
| `dbg_eval(expression)` | Evaluate any AHK expression in the current context. |
| `dbg_get_source(file, begin_line, end_line)` | Retrieve source code from the debugged script. |

#### Breakpoints
| Tool | Description |
|---|---|
| `dbg_set_breakpoint(file, line)` | Set a line breakpoint. |
| `dbg_list_breakpoints()` | List all active breakpoints. |
| `dbg_remove_breakpoint(breakpoint_id)` | Remove a breakpoint by ID. |

#### I/O
| Tool | Description |
|---|---|
| `dbg_stdout(mode)` | Redirect script stdout to the debugger: `0`=disable, `1`=copy, `2`=redirect. |

---

## Example Workflows

### Basic: Write and Validate a Script

**User:** "Write a script that closes my active window and logs it using my `MyLogger.ahk` library."

**AI Process (Under the hood):**
1. **AI calls `inspect_active_window`** -> Finds out the user is in "Notepad" (`ahk_class Notepad`).
2. **AI calls `search_global_library("MyLogger")`** -> Discovers it needs to use `Logger.Info("Closed")`.
3. **AI writes the draft script.**
4. **AI calls `validate_ahk_syntax`** -> Realizes it forgot a closing brace.
5. **AI fixes the code and gives the user a guaranteed-to-work script.**

### Advanced: Debug a Stuck Script

**User:** "My script PID 12345 seems stuck. Can you figure out why?"

**AI Process:**
1. **AI calls `dbg_attach(pid=12345)`** -> Connects to the running script.
2. **AI calls `dbg_break()`** -> Pauses execution.
3. **AI calls `dbg_stack()`** -> Sees script is stuck in `MyFunction()` at line 42.
4. **AI calls `dbg_get_vars(context=0)`** -> Inspects local variables, finds `retryCount = 999`.
5. **AI calls `dbg_eval("retryCount := 0")`** -> Resets the counter.
6. **AI calls `dbg_continue(mode="run")`** -> Resumes the script.
7. **AI calls `dbg_detach()`** -> Disconnects cleanly.
8. **AI explains:** "Your script was stuck in an infinite retry loop. I reset `retryCount` to 0."

---

## Installation

1. Install Python 3.10+.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure your AutoHotkey and Library paths using the `configure_paths` tool.

---

## Connecting to Antigravity

Antigravity can leverage this server to provide expert AutoHotkey assistance. To connect this server to your Antigravity instance, add it to your `antigravity.json` or your global MCP configuration:

```json
{
  "mcpServers": {
    "ahk-v2-server": {
      "command": "python",
      "args": ["path/to/server.py"],
      "env": {
        "AHK_PATH": "C:\\Program Files\\AutoHotkey\\v2\\AutoHotkey64.exe",
        "GLOBAL_LIB_PATH": "C:\\Users\\YourUser\\Documents\\AutoHotkey\\Lib"
      }
    }
  }
}
```
### Zero Configuration (Antigravity Only)
If you are an **Antigravity** user, you can skip manual JSON editing:
1. **Clone** this repository locally.
2. Open an Antigravity chat and tell it the **absolute path** to the repo.
3. Ask it to: *"Connect to the MCP server in this directory."*

**The Experience:**
Once connected, try asking:
> *"Can you use the AutoHotkey v2 MCP? How does it feel to have these tools at your disposal?"*

You will see that with these "eyes and hands," Antigravity's ability to automate your Windows environment becomes exponentially more effective—transforming from a guessing assistant into a precise systems architect.

### What can you ask Antigravity?
Once connected, you can leverage the full power of AutoHotkey through simple prompts:
- **System Awareness**: *"Inspect my active window and tell me its class."*
- **Live Debugging**: *"Attach to my script (PID 1234) and find out why it's stuck."*
- **Library Integration**: *"Write a new automation script using my existing local libraries."*
- **Office Automation**: *"Highlight row X on my active Excel workbook using ComObject."*
- **Web Automation**: *"Use Rufaydium to create a Chrome session and inspect the target webpage."*
- **Error Resolution**: *"I have an AutoHotkey error popup; please diagnose and fix it."*
- **Complex Workflows**: *"Scan my document, extract all keywords, and create a summary table in a new Excel workbook."*

---

## License
This project is licensed under the **GNU GPL 3.0**. See the [LICENSE](LICENSE) file for details.
