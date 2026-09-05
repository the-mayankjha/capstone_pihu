"""
Bidirectional JSON-lines IPC protocol over standard I/O between Python and Rust.
"""

import sys
import json
import asyncio
import logging
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger("PIHU.IPC")


class IpcProtocol:
    """Manages asynchronous JSON-lines IPC over stdin and stdout."""

    def __init__(self):
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._running = False
        self._reader_task: Optional[asyncio.Task] = None

    def register_handler(self, event_type: str, handler: Callable[[Dict[str, Any]], Any]):
        """Register a callback for an incoming command type from Rust."""
        self._handlers[event_type] = handler

    def send_event(self, event_type: str, **kwargs):
        """Send a JSON event to Rust via stdout with immediate flushing."""
        payload = {"type": event_type, **kwargs}
        line = json.dumps(payload) + "\n"
        try:
            sys.stdout.write(line)
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Failed to send IPC event: {e}")

    async def start(self):
        """Start reading incoming JSON commands from stdin asynchronously."""
        self._running = True
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        self._reader_task = asyncio.create_task(self._read_loop(reader))
        logger.info("IPC Protocol listener started.")

    async def _read_loop(self, reader: asyncio.StreamReader):
        while self._running:
            try:
                line_bytes = await reader.readline()
                if not line_bytes:
                    logger.info("Stdin closed, exiting IPC read loop.")
                    break
                line = line_bytes.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    cmd_type = data.get("type")
                    if cmd_type in self._handlers:
                        handler = self._handlers[cmd_type]
                        if asyncio.iscoroutinefunction(handler):
                            asyncio.create_task(handler(data))
                        else:
                            handler(data)
                    else:
                        logger.warning(f"No handler registered for command: {cmd_type}")
                except json.JSONDecodeError as err:
                    logger.error(f"Invalid JSON received on stdin: '{line}' ({err})")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in IPC read loop: {e}")

    async def stop(self):
        """Stop IPC protocol listener."""
        self._running = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        logger.info("IPC Protocol stopped.")
