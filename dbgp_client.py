"""
DBGp Client for AutoHotkey — Pure Python implementation.

Implements the DBGp protocol (https://xdebug.org/docs/dbgp) to connect
to running AutoHotkey scripts as a debug client (IDE side).

Flow:
  1. Start TCP listener on a port
  2. Send AHK_ATTACH_DEBUGGER window message to the target script (via AHK helper)
  3. Target script connects back → we receive the init packet
  4. Send DBGp commands (step, break, eval, context_get, etc.)
  5. Receive XML responses
"""

import socket
import base64
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import unquote as url_unquote
from dataclasses import dataclass, field
import threading
import time
import logging

logger = logging.getLogger("dbgp_client")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DbgpVariable:
    """Represents a variable from a DBGp context_get / property_get response."""
    name: str
    fullname: str
    type: str
    value: Optional[str] = None
    classname: Optional[str] = None
    address: Optional[str] = None
    size: Optional[int] = None
    children: List["DbgpVariable"] = field(default_factory=list)
    facet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "fullname": self.fullname,
            "type": self.type,
        }
        if self.value is not None:
            d["value"] = self.value
        if self.classname:
            d["classname"] = self.classname
        if self.address:
            d["address"] = self.address
        if self.size is not None:
            d["size"] = self.size
        if self.facet:
            d["facet"] = self.facet
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


@dataclass
class DbgpStackFrame:
    """Represents a single stack frame from stack_get."""
    level: int
    type: str
    filename: str
    lineno: int
    where: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "level": self.level,
            "type": self.type,
            "filename": self.filename,
            "lineno": self.lineno,
        }
        if self.where:
            d["where"] = self.where
        return d


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DbgpError(Exception):
    """Error from the DBGp debugger engine."""
    def __init__(self, code: int, message: str = ""):
        self.code = code
        super().__init__(f"DBGp error {code}: {message}")


class DbgpConnectionError(Exception):
    """Connection-level error."""
    pass


# ---------------------------------------------------------------------------
# Protocol helpers
# ---------------------------------------------------------------------------

def _b64_encode(text: str) -> str:
    """Base64-encode a UTF-8 string."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _b64_decode(data: str) -> str:
    """Base64-decode to a UTF-8 string."""
    if not data:
        return ""
    return base64.b64decode(data).decode("utf-8", errors="replace")


def _decode_file_uri(uri: str) -> str:
    """Convert file:///C:/path to C:\\path, decoding percent-encoded chars."""
    if uri.startswith("file:///"):
        uri = uri[8:]
    uri = url_unquote(uri)
    return uri.replace("/", "\\")


def _encode_file_uri(path: str) -> str:
    """Convert C:\\path to file:///C:/path."""
    path = path.replace("\\", "/")
    if not path.startswith("file:///"):
        path = "file:///" + path
    return path


def _parse_property(elem: ET.Element) -> DbgpVariable:
    """Parse a <property> XML element into a DbgpVariable."""
    name = elem.get("name", "")
    fullname = elem.get("fullname", name)
    vtype = elem.get("type", "undefined")
    classname = elem.get("classname")
    address = elem.get("address")
    facet = elem.get("facet")
    size_str = elem.get("size")
    size = int(size_str) if size_str else None

    value = None
    encoding = elem.get("encoding", "none")
    if vtype != "object" and vtype != "undefined":
        raw_text = elem.text or ""
        if encoding == "base64":
            value = _b64_decode(raw_text)
        else:
            value = raw_text

    children = []
    for child_elem in elem.findall("property"):
        children.append(_parse_property(child_elem))

    return DbgpVariable(
        name=name,
        fullname=fullname,
        type=vtype,
        value=value,
        classname=classname,
        address=address,
        size=size,
        children=children,
        facet=facet,
    )


# ---------------------------------------------------------------------------
# DbgpClient — the main client class
# ---------------------------------------------------------------------------

class DbgpClient:
    """
    Pure-Python DBGp client.

    Usage:
        client = DbgpClient()
        client.start_listening(port=9005)
        # ... trigger AHK_ATTACH_DEBUGGER externally ...
        client.accept_connection(timeout=5)
        # Now send commands:
        status = client.status()
        variables = client.context_get(context_id=1)
        client.close()
    """

    DEFAULT_PORT = 9005

    def __init__(self):
        self._server_socket: Optional[socket.socket] = None
        self._conn_socket: Optional[socket.socket] = None
        self._port: int = 0
        self._txn_id: int = 0
        self._recv_buf: bytes = b""
        self._continuation_pending: bool = False  # True when run/step sent, response not yet read

        # Session info (populated after init packet)
        self.connected: bool = False
        self.file: Optional[str] = None
        self.thread: Optional[int] = None
        self.ide_key: Optional[str] = None
        self.app_id: Optional[str] = None
        self.language: Optional[str] = None
        self._init_xml: Optional[str] = None

    @property
    def port(self) -> int:
        return self._port

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def start_listening(self, port: int = DEFAULT_PORT, host: str = "127.0.0.1"):
        """Start a TCP listener for incoming DBGp connections."""
        if self._server_socket:
            raise DbgpConnectionError("Already listening")

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(1)
        self._server_socket = srv
        self._port = port
        logger.info(f"DBGp listening on {host}:{port}")

    def accept_connection(self, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Wait for a debugger engine to connect.
        Returns parsed init packet info.
        Raises DbgpConnectionError on timeout.
        """
        if not self._server_socket:
            raise DbgpConnectionError("Not listening — call start_listening() first")
        if self._conn_socket:
            raise DbgpConnectionError("Already connected — close first")

        self._server_socket.settimeout(timeout)
        try:
            conn, addr = self._server_socket.accept()
        except socket.timeout:
            raise DbgpConnectionError(
                f"No debugger engine connected within {timeout}s. "
                "Ensure the target AHK script received the AHK_ATTACH_DEBUGGER message."
            )

        conn.settimeout(5.0)
        self._conn_socket = conn
        self._recv_buf = b""
        logger.info(f"DBGp connection from {addr}")

        # Read the init packet
        init_xml = self._recv_packet()
        self._init_xml = init_xml

        root = ET.fromstring(init_xml)
        self.file = _decode_file_uri(root.get("fileuri", ""))
        thread_str = root.get("thread", "0")
        self.thread = int(thread_str) if thread_str.isdigit() else 0
        self.ide_key = root.get("ide_key", "")
        self.app_id = root.get("appid", "")
        self.language = root.get("language", "")
        self.connected = True

        logger.info(f"DBGp session: file={self.file}, thread={self.thread}")

        return {
            "status": "connected",
            "file": self.file,
            "thread": self.thread,
            "ide_key": self.ide_key,
            "app_id": self.app_id,
            "language": self.language,
        }

    def close(self):
        """Close the debug session and stop listening."""
        if self._conn_socket:
            try:
                self._conn_socket.close()
            except Exception:
                pass
            self._conn_socket = None

        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None

        self.connected = False
        self.file = None
        self.thread = None
        self._recv_buf = b""
        logger.info("DBGp session closed")

    # ------------------------------------------------------------------
    # Low-level protocol I/O
    # ------------------------------------------------------------------

    def _next_txn_id(self) -> str:
        self._txn_id += 1
        return str(self._txn_id)

    def _send_raw(self, command: str, args: str = "", data: Optional[str] = None) -> str:
        """Send a DBGp command packet. Returns the transaction ID."""
        if not self._conn_socket:
            raise DbgpConnectionError("Not connected")

        txn_id = self._next_txn_id()
        packet = f"{command} -i {txn_id}"
        if args:
            packet += f" {args}"
        if data is not None:
            packet += f" -- {_b64_encode(data)}"

        raw = packet.encode("utf-8") + b"\0"
        self._conn_socket.sendall(raw)
        logger.debug(f"SEND: {packet}")
        return txn_id

    def _recv_and_check(self) -> str:
        """Receive one DBGp packet and check for errors."""
        response_xml = self._recv_packet()
        logger.debug(f"RECV: {response_xml[:200]}")

        root = ET.fromstring(response_xml)
        error_elem = root.find("error")
        if error_elem is not None:
            code = int(error_elem.get("code", "0"))
            msg_elem = error_elem.find("message")
            msg = msg_elem.text if msg_elem is not None and msg_elem.text else ""
            raise DbgpError(code, msg)

        return response_xml

    def _send_command(self, command: str, args: str = "", data: Optional[str] = None) -> str:
        """
        Send a DBGp command and return the raw XML response (synchronous).
        Format: command -i txn_id [args] [-- base64(data)]\0
        """
        self._send_raw(command, args, data)
        return self._recv_and_check()

    def _send_continuation(self, command: str) -> Dict[str, str]:
        """
        Send a continuation command (run/step_into/step_over/step_out).
        For 'run': fire-and-forget (response comes later on break).
        For 'step_*': wait for response (they complete quickly).
        """
        self._send_raw(command)
        self._continuation_pending = True

        if command == "run":
            # Don't wait — the response arrives when the script breaks.
            return {"status": "running", "reason": "ok"}

        # Step commands complete quickly (one line), so we can wait.
        try:
            xml = self._recv_and_check()
            self._continuation_pending = False
            root = ET.fromstring(xml)
            return {
                "status": root.get("status", "unknown"),
                "reason": root.get("reason", ""),
            }
        except Exception:
            self._continuation_pending = False
            raise

    def _recv_packet(self) -> str:
        """
        Receive one DBGp response packet.
        Wire format: length_string \0 xml_data \0
        """
        if not self._conn_socket:
            raise DbgpConnectionError("Not connected")

        # Read until we have the length header (null-terminated number)
        while b"\0" not in self._recv_buf:
            chunk = self._conn_socket.recv(8192)
            if not chunk:
                raise DbgpConnectionError("Connection closed by debugger engine")
            self._recv_buf += chunk

        null_pos = self._recv_buf.index(b"\0")
        length_str = self._recv_buf[:null_pos].decode("utf-8")
        self._recv_buf = self._recv_buf[null_pos + 1:]

        if not length_str.isdigit():
            raise DbgpConnectionError(f"Invalid packet header: {length_str!r}")

        packet_len = int(length_str)

        # Read the XML body + trailing null
        needed = packet_len + 1  # +1 for trailing \0
        while len(self._recv_buf) < needed:
            chunk = self._conn_socket.recv(8192)
            if not chunk:
                raise DbgpConnectionError("Connection closed while reading packet body")
            self._recv_buf += chunk

        xml_data = self._recv_buf[:packet_len].decode("utf-8")
        self._recv_buf = self._recv_buf[needed:]  # skip past trailing \0

        return xml_data

    # ------------------------------------------------------------------
    # High-level DBGp commands
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, str]:
        """Get debugger status. Returns {status, reason}."""
        xml = self._send_command("status")
        root = ET.fromstring(xml)
        return {
            "status": root.get("status", "unknown"),
            "reason": root.get("reason", ""),
        }

    def feature_get(self, name: str) -> Dict[str, Any]:
        """Query a feature from the debugger engine."""
        xml = self._send_command("feature_get", f"-n {name}")
        root = ET.fromstring(xml)
        return {
            "feature": name,
            "supported": root.get("supported", "0") == "1",
            "value": root.text or "",
        }

    def feature_set(self, name: str, value: str) -> bool:
        """Set a feature on the debugger engine."""
        xml = self._send_command("feature_set", f"-n {name} -v {value}")
        root = ET.fromstring(xml)
        return root.get("success", "0") == "1"

    def run(self) -> Dict[str, str]:
        """Continue execution (fire-and-forget — response comes on break)."""
        return self._send_continuation("run")

    def step_into(self) -> Dict[str, str]:
        """Step into the next statement."""
        return self._send_continuation("step_into")

    def step_over(self) -> Dict[str, str]:
        """Step over the next statement."""
        return self._send_continuation("step_over")

    def step_out(self) -> Dict[str, str]:
        """Step out of the current function."""
        return self._send_continuation("step_out")

    def stop(self) -> Dict[str, str]:
        """Stop/end the debug session (kills the script)."""
        xml = self._send_command("stop")
        root = ET.fromstring(xml)
        return {
            "status": root.get("status", "unknown"),
            "reason": root.get("reason", ""),
        }

    def detach(self) -> Dict[str, str]:
        """Detach from the script (lets it continue without debugger)."""
        xml = self._send_command("detach")
        root = ET.fromstring(xml)
        return {
            "status": root.get("status", "unknown"),
            "reason": root.get("reason", ""),
        }

    def breakpoint_set(
        self,
        file: str,
        line: int,
        type: str = "line",
        state: str = "enabled",
        temporary: bool = False,
        expression: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Set a breakpoint. Returns breakpoint info including its ID."""
        file_uri = _encode_file_uri(file)
        args = f"-t {type} -f {file_uri} -n {line} -s {state}"
        if temporary:
            args += " -r 1"

        data = expression if expression else None
        xml = self._send_command("breakpoint_set", args, data)
        root = ET.fromstring(xml)
        return {
            "id": root.get("id", ""),
            "state": root.get("state", state),
        }

    def breakpoint_get(self, breakpoint_id: str) -> Dict[str, Any]:
        """Get info about a specific breakpoint."""
        xml = self._send_command("breakpoint_get", f"-d {breakpoint_id}")
        root = ET.fromstring(xml)
        bp = root.find("breakpoint")
        if bp is None:
            return {"id": breakpoint_id, "error": "not found"}
        return {
            "id": bp.get("id", ""),
            "type": bp.get("type", ""),
            "filename": _decode_file_uri(bp.get("filename", "")),
            "lineno": int(bp.get("lineno", "0")),
            "state": bp.get("state", ""),
            "hit_count": int(bp.get("hit_count", "0")),
        }

    def breakpoint_remove(self, breakpoint_id: str) -> bool:
        """Remove a breakpoint by ID."""
        self._send_command("breakpoint_remove", f"-d {breakpoint_id}")
        return True

    def breakpoint_list(self) -> List[Dict[str, Any]]:
        """List all breakpoints."""
        xml = self._send_command("breakpoint_list")
        root = ET.fromstring(xml)
        result = []
        for bp in root.findall("breakpoint"):
            result.append({
                "id": bp.get("id", ""),
                "type": bp.get("type", ""),
                "filename": _decode_file_uri(bp.get("filename", "")),
                "lineno": int(bp.get("lineno", "0")),
                "state": bp.get("state", ""),
                "hit_count": int(bp.get("hit_count", "0")),
            })
        return result

    def stack_depth(self) -> int:
        """Get the maximum stack depth."""
        xml = self._send_command("stack_depth")
        root = ET.fromstring(xml)
        return int(root.get("depth", "0"))

    def stack_get(self, depth: Optional[int] = None) -> List[DbgpStackFrame]:
        """Get stack frames. If depth specified, returns just that level."""
        args = f"-d {depth}" if depth is not None else ""
        xml = self._send_command("stack_get", args)
        root = ET.fromstring(xml)
        frames = []
        for stack_elem in root.findall("stack"):
            frames.append(DbgpStackFrame(
                level=int(stack_elem.get("level", "0")),
                type=stack_elem.get("type", "file"),
                filename=_decode_file_uri(stack_elem.get("filename", "")),
                lineno=int(stack_elem.get("lineno", "0")),
                where=stack_elem.get("where"),
            ))
        return frames

    def context_names(self, depth: int = 0) -> List[Dict[str, Any]]:
        """Get available context names at a given stack depth."""
        xml = self._send_command("context_names", f"-d {depth}")
        root = ET.fromstring(xml)
        result = []
        for ctx in root.findall("context"):
            result.append({
                "name": ctx.get("name", ""),
                "id": int(ctx.get("id", "0")),
            })
        return result

    def context_get(self, context_id: int = 0, depth: int = 0) -> List[DbgpVariable]:
        """Get all variables in a given context at a given stack depth."""
        xml = self._send_command("context_get", f"-c {context_id} -d {depth}")
        root = ET.fromstring(xml)
        variables = []
        for prop in root.findall("property"):
            variables.append(_parse_property(prop))
        return variables

    def property_get(self, name: str, context_id: int = 0, depth: int = 0) -> DbgpVariable:
        """Get a single property/variable by name."""
        xml = self._send_command("property_get", f"-n {name} -c {context_id} -d {depth}")
        root = ET.fromstring(xml)
        prop = root.find("property")
        if prop is None:
            raise DbgpError(300, f"Property '{name}' not found")
        return _parse_property(prop)

    def property_set(self, name: str, value: str, type: str = "string", depth: int = 0) -> bool:
        """Set a variable's value."""
        args = f"-n {name} -d {depth} -t {type}"
        xml = self._send_command("property_set", args, data=value)
        root = ET.fromstring(xml)
        return root.get("success", "0") == "1"

    def eval(self, expression: str) -> Optional[DbgpVariable]:
        """Evaluate an expression in the current context."""
        xml = self._send_command("eval", data=expression)
        root = ET.fromstring(xml)
        prop = root.find("property")
        if prop is not None:
            return _parse_property(prop)
        return None

    def source(self, file: Optional[str] = None, begin_line: int = 0, end_line: int = 0) -> str:
        """Get source code. If file is None, gets current file."""
        args = ""
        if file:
            args += f"-f {_encode_file_uri(file)}"
        if begin_line > 0:
            args += f" -b {begin_line}"
        if end_line > 0:
            args += f" -e {end_line}"
        xml = self._send_command("source", args)
        root = ET.fromstring(xml)
        encoding = root.get("encoding", "none")
        raw = root.text or ""
        if encoding == "base64":
            return _b64_decode(raw)
        return raw

    def stdout(self, mode: int = 1) -> bool:
        """Set stdout redirection: 0=disable, 1=copy, 2=redirect."""
        xml = self._send_command("stdout", f"-c {mode}")
        root = ET.fromstring(xml)
        return root.get("success", "0") == "1"

    def stderr(self, mode: int = 1) -> bool:
        """Set stderr redirection: 0=disable, 1=copy, 2=redirect."""
        xml = self._send_command("stderr", f"-c {mode}")
        root = ET.fromstring(xml)
        return root.get("success", "0") == "1"

    def send_break(self) -> Dict[str, Any]:
        """
        Send async break command to pause a running script.
        Also collects the pending continuation response if one exists.
        """
        # Send the break command
        self._send_raw("break")

        # We may receive two responses:
        # 1. The break response (success/failure)
        # 2. The pending continuation response (run/step completed)
        # AutoHotkey sends the break response first, then the continuation response.
        break_xml = self._recv_and_check()
        break_root = ET.fromstring(break_xml)
        success = break_root.get("success", "0") == "1"

        # Now read the pending continuation response
        if self._continuation_pending:
            try:
                cont_xml = self._recv_and_check()
                self._continuation_pending = False
                cont_root = ET.fromstring(cont_xml)
                return {
                    "success": success,
                    "status": cont_root.get("status", "break"),
                    "reason": cont_root.get("reason", "ok"),
                }
            except Exception:
                self._continuation_pending = False

        return {"success": success, "status": "break", "reason": "ok"}


# ---------------------------------------------------------------------------
# Module-level singleton for MCP server integration
# ---------------------------------------------------------------------------

_active_client: Optional[DbgpClient] = None


def get_active_client() -> Optional[DbgpClient]:
    """Get the current active DBGp client, or None."""
    return _active_client


def set_active_client(client: Optional[DbgpClient]):
    """Set the active DBGp client singleton."""
    global _active_client
    _active_client = client
