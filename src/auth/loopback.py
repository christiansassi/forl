"""The one request the browser makes back to this process.

The redirect that carries the authorization code goes to a loopback address, so
the code is handed from the browser to this process without crossing the
network at all. A server is opened on the port the authorization request will
name, waits for the one request it asked for, tells whoever is looking at the
browser that they can close the tab, and shuts down.

The port is taken before the browser is opened, which is the reason this is a
class and not a function: a browser that arrived at a port nothing was listening
on would show a connection error and the code would be lost. A caller that does
not care which port it gets asks for port 0 and reads back the one the system
gave, which is what a provider accepting any loopback port allows.

Connections are handled on threads of their own, and this is not an
optimization. Browsers open connections ahead of time and send nothing down
them; a server handling one connection at a time would block inside such a
connection, reading a request line that never comes, while the redirect it is
waiting for sat unaccepted. Every connection also has a deadline, so one that
says nothing is dropped rather than left holding a thread.
"""

from __future__ import annotations

import http.server
import socket
import socketserver
import threading
import time
import urllib.parse
from typing import NamedTuple

from ..validation import require_non_empty_str, require_number_in_range, require_type

HOST = "127.0.0.1"

# Port 0 asks the system for whichever port is free.
ANY_PORT = 0

# How long a single accept waits before the loop checks the deadline again.
# Short enough that a caller's timeout is honored to about a second.
POLL_SECONDS = 0.5

# How long one connection may take to send its request line. A browser
# preconnect sends nothing at all and would otherwise hold a thread until the
# whole sign-in gave up.
CONNECTION_SECONDS = 15.0

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>
html{{color-scheme:dark light}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;
font:16px/1.5 -apple-system,Segoe UI,system-ui,sans-serif}}
main{{text-align:center;padding:2rem}}
h1{{font-size:1.25rem;margin:0 0 .5rem}}
p{{margin:0;opacity:.7}}
</style></head>
<body><main><h1>{title}</h1><p>{detail}</p></main></body></html>
"""

DONE_TITLE = "Signed in"
DONE_DETAIL = "You can close this tab and go back to the widget."
FAILED_TITLE = "Sign-in was not completed"
FAILED_DETAIL = "Go back to the widget and try again."
STRAY_TITLE = "Not here"
STRAY_DETAIL = "This address is not part of signing in."


class Redirect(NamedTuple):
	"""What the browser came back with.

	Attributes:
		code: The authorization code, empty when the provider sent none. str.
		state: The state value the provider echoed back. str.
		error: What the provider said went wrong, empty when nothing did. str.
	"""

	code: str
	state: str
	error: str


class _Server(socketserver.ThreadingTCPServer):
	"""A loopback server that keeps the one redirect it is waiting for."""

	# Left at the default so that a port already in use is reported as such
	# rather than quietly shared, which on Windows it otherwise can be.
	allow_reuse_address = False
	daemon_threads = True
	# Closing does not wait for threads, because the one thread that matters has
	# already finished writing its answer by the time the wait returns.
	block_on_close = False

	def __init__(self, port: int, path: str) -> None:
		"""Bind the port and prepare to catch one redirect.

		Args:
			port: Loopback port to listen on, or 0 for any free one. int, 0 or
				more.
			path: Path of the redirect to answer, such as "/callback". str,
				non-empty.

		Returns:
			None.
		"""
		self.wanted_path = path
		self.caught: Redirect | None = None
		self.arrived = threading.Event()
		super().__init__((HOST, port), _Handler)


class _Handler(http.server.BaseHTTPRequestHandler):
	"""Answers the redirect, and answers anything else with a 404."""

	# The provider's redirect is a plain GET, and HTTP/1.0 lets the response be
	# ended by closing the connection, so no length juggling is needed.
	protocol_version = "HTTP/1.0"
	timeout = CONNECTION_SECONDS

	def log_message(self, format: str, *args: object) -> None:
		"""Drop the access log the base class would write to the error stream.

		Args:
			format: The printf style template the base class passes. str.
			*args: Its arguments. object.

		Returns:
			None.
		"""

	def _reply(self, status: int, title: str, detail: str) -> None:
		"""Send one HTML page and push it out to the browser.

		Args:
			status: HTTP status to send. int.
			title: Heading of the page. str.
			detail: Line under the heading. str.

		Returns:
			None.
		"""
		body = PAGE.format(title=title, detail=detail).encode("utf-8")
		self.send_response(status)
		self.send_header("Content-Type", "text/html; charset=utf-8")
		self.send_header("Content-Length", str(len(body)))
		self.end_headers()
		self.wfile.write(body)
		self.wfile.flush()

	def do_GET(self) -> None:
		"""Catch the redirect, or answer anything else with a 404.

		Returns:
			None.
		"""
		parts = urllib.parse.urlsplit(self.path)
		if parts.path != self.server.wanted_path:
			# A browser asks for /favicon.ico on its own account. Answering that
			# with the sign-in result would consume the one request the caller
			# is waiting for.
			self._reply(404, STRAY_TITLE, STRAY_DETAIL)
			return

		query = urllib.parse.parse_qs(parts.query)
		caught = Redirect(
			code=(query.get("code") or [""])[0],
			state=(query.get("state") or [""])[0],
			error=(query.get("error_description") or query.get("error") or [""])[0],
		)
		if caught.code and not caught.error:
			self._reply(200, DONE_TITLE, DONE_DETAIL)
		else:
			self._reply(200, FAILED_TITLE, FAILED_DETAIL)

		# Recorded only once the page is on its way, so the caller can close the
		# port the moment it sees this without cutting the answer short.
		self.server.caught = caught
		self.server.arrived.set()


class RedirectCatcher:
	"""A loopback port, held open, waiting for one authorization redirect."""

	def __init__(self, port: int, path: str) -> None:
		"""Take a port now, so the browser has somewhere to come back to.

		Args:
			port: Loopback port to listen on, or 0 to be given any free one.
				int, 0 or more.
			path: Path of the redirect, such as "/callback". str, non-empty.

		Returns:
			None.

		Raises:
			OSError: When the port cannot be taken, which for a port asked for
				by number usually means something else is already listening.
		"""
		require_type(port, int, "port")
		if port < 0:
			raise ValueError("port must be 0 or more")
		require_non_empty_str(path, "path")
		self._server = _Server(port, path)

	@property
	def port(self) -> int:
		"""Return the port actually being listened on.

		Returns:
			int: The port, which is the one asked for unless that was 0, in
			which case it is the one the system gave.
		"""
		return int(self._server.server_address[1])

	def __enter__(self) -> RedirectCatcher:
		"""Return this catcher, for use as a context manager.

		Returns:
			RedirectCatcher: This object.
		"""
		return self

	def __exit__(self, *_exception: object) -> None:
		"""Give the port back.

		Args:
			*_exception: The exception being propagated, if any, which does not
				change what happens here. object.

		Returns:
			None.
		"""
		self.close()

	def close(self) -> None:
		"""Stop listening and release the port.

		Returns:
			None.
		"""
		self._server.server_close()

	def wait(self, timeout: float) -> Redirect | None:
		"""Serve requests until the redirect arrives or the time runs out.

		Args:
			timeout: How long to wait in total, in seconds. float, between 1
				and 900.

		Returns:
			Redirect or None: What the browser came back with, or None when
			nothing did within the time allowed.
		"""
		require_number_in_range(timeout, 1.0, 900.0, "timeout")

		deadline = time.monotonic() + timeout
		self._server.timeout = POLL_SECONDS
		while not self._server.arrived.is_set() and time.monotonic() < deadline:
			try:
				self._server.handle_request()
			except OSError:
				# A browser that opened a connection and dropped it is not a
				# reason to abandon the sign-in; the real redirect may still be
				# on its way.
				continue
		return self._server.caught


def port_is_free(port: int) -> bool:
	"""Return whether a loopback port can be listened on right now.

	Asked before the browser is opened, for a provider that accepts only one
	port, so the user is told which program to close rather than being sent to
	a page whose answer will be dropped.

	Args:
		port: The loopback port to try. int, 1 or more.

	Returns:
		bool: True when nothing is listening on it.
	"""
	require_type(port, int, "port")
	if port < 1:
		raise ValueError("port must be 1 or more")

	probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	try:
		probe.bind((HOST, port))
	except OSError:
		return False
	finally:
		probe.close()
	return True
