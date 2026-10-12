//
//  LoopbackServer.swift
//  The one request the browser makes back to this process.
//
//  The redirect that carries the authorization code goes to a loopback address,
//  so the code is handed from the browser to this process without crossing the
//  network at all. A listener is opened on the port the authorization request
//  will name, waits for the one request it asked for, tells whoever is looking
//  at the browser that they can close the tab, and shuts down.
//
//  The port is taken before the browser is opened, which is why this is started
//  in two steps: a browser that arrived at a port nothing was listening on would
//  show a connection error and the code would be lost. A caller that does not
//  care which port it gets asks for port 0 and reads back the one the system
//  gave, which is what a provider accepting any loopback port allows.
//
//  Anything that is not the redirect is answered with a 404 rather than with
//  the sign-in result. A browser asks for /favicon.ico on its own account, and
//  answering that with the result would consume the one request being waited on.
//

import Foundation
import Network
import os

/// Port 0 asks the system for whichever port is free.
let anyPort: UInt16 = 0

private let log = Logger(subsystem: "io.forl.app", category: "loopback")

/// What the browser came back with.
struct Redirect: Sendable {
	/// The authorization code, empty when the provider sent none.
	var code: String = ""
	/// The state value the provider echoed back.
	var state: String = ""
	/// What the provider said went wrong, empty when nothing did.
	var error: String = ""
	/// Whether the code came from the hosted manual callback.
	var manual = false
}

/// A loopback port, held open, waiting for one authorization redirect.
final class LoopbackServer: @unchecked Sendable {
	private let listener: NWListener
	private let wantedPath: String
	private let queue = DispatchQueue(label: "io.forl.loopback")
	private var continuation: CheckedContinuation<Redirect, Error>?
	private var result: Result<Redirect, Error>?

	/// Take a port now, so the browser has somewhere to come back to.
	///
	/// - Parameters:
	///   - port: Loopback port to listen on, or `anyPort` to be given any free
	///     one.
	///   - path: Path of the redirect, such as "/callback".
	/// - Returns: Nothing.
	/// - Throws: `UsageError.credentials` when the port cannot be taken, which
	///   for a port asked for by number usually means something else is already
	///   listening on it.
	init(port: UInt16, path: String) throws {
		wantedPath = path
		let parameters = NWParameters.tcp
		parameters.requiredLocalEndpoint = NWEndpoint.hostPort(host: .ipv4(.loopback), port: .init(rawValue: port)!)
		parameters.allowLocalEndpointReuse = false

		do {
			listener = try NWListener(using: parameters)
		} catch {
			throw UsageError.credentials("Cannot listen on port \(port): \(error.localizedDescription)")
		}
	}

	/// Return the port actually being listened on.
	///
	/// - Returns: The port, which is the one asked for unless that was
	///   `anyPort`, in which case it is the one the system gave.
	var port: UInt16 {
		listener.port?.rawValue ?? 0
	}

	/// Begin listening, so the port is held before the browser is opened.
	///
	/// - Returns: Nothing, once the listener is ready.
	/// - Throws: `UsageError.credentials` when the listener fails to start.
	func start() async throws {
		try await withCheckedThrowingContinuation { (ready: CheckedContinuation<Void, Error>) in
			var resumed = false
			listener.stateUpdateHandler = { state in
				guard !resumed else {
					return
				}
				switch state {
				case .ready:
					resumed = true
					ready.resume()
				case .failed(let error):
					resumed = true
					ready.resume(throwing: UsageError.credentials(
						"Cannot listen for the sign-in: \(error.localizedDescription)"
					))
				default:
					break
				}
			}
			listener.newConnectionHandler = { [weak self] connection in
				self?.accept(connection)
			}
			listener.start(queue: queue)
		}
	}

	/// Wait for the redirect to arrive.
	///
	/// - Parameter timeout: How long to wait in total, in seconds.
	/// - Returns: What the browser came back with.
	/// - Throws: `UsageError.credentials` when nothing arrives in time.
	func wait(timeout: TimeInterval) async throws -> Redirect {
		guard timeout.isFinite, (1...900).contains(timeout) else {
			throw UsageError.credentials("timeout must be between 1 and 900 seconds.")
		}
		return try await withTaskCancellationHandler {
			try await withCheckedThrowingContinuation { waiting in
				queue.async { [self] in
					if let result {
						waiting.resume(with: result)
						return
					}
					continuation = waiting
					queue.asyncAfter(deadline: .now() + timeout) { [weak self] in
						self?.finish(.failure(UsageError.credentials("Sign-in was not completed.")))
					}
				}
			}
		} onCancel: {
			self.queue.async { [self] in finish(.failure(CancellationError())) }
		}
	}

	/// Submit the browser's full code to the current sign-in wait.
	///
	/// - Parameters:
	///   - code: The pasted authorization code in code#state form.
	///   - expectedState: The state generated for this sign-in.
	/// - Returns: Whether this code completed the pending wait.
	/// - Throws: `UsageError.credentials` when code is malformed or from another sign-in.
	func submitCode(_ code: String, expectedState: String) throws -> Bool {
		guard !expectedState.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
			throw UsageError.credentials("expectedState must not be empty.")
		}
		let value = code.trimmingCharacters(in: .whitespacesAndNewlines)
		let parts = value.components(separatedBy: "#")
		guard parts.count == 2, !parts[0].isEmpty, !parts[1].isEmpty, value.rangeOfCharacter(from: .whitespacesAndNewlines) == nil else {
			throw UsageError.credentials("code is incomplete. Copy the full authorization code from the browser.")
		}
		guard parts[1] == expectedState else {
			throw UsageError.credentials("code belongs to another sign-in. Copy the code from the current browser tab.")
		}
		return queue.sync {
			guard result == nil else { return false }
			finish(.success(Redirect(code: parts[0], state: expectedState, manual: true)))
			return true
		}
	}

	/// Record the first answer, including one received before wait starts.
	///
	/// - Parameter outcome: The redirect or failure to deliver on the listener queue.
	/// - Returns: Nothing.
	private func finish(_ outcome: Result<Redirect, Error>) {
		guard result == nil else { return }
		result = outcome
		continuation?.resume(with: outcome)
		continuation = nil
	}

	/// Stop listening and give the port back.
	///
	/// - Returns: Nothing.
	func close() {
		listener.cancel()
		queue.async { [self] in finish(.failure(CancellationError())) }
	}

	/// Read one connection's request line and answer it.
	///
	/// Browsers open connections ahead of time and send nothing down them, so a
	/// connection is read for as long as it takes to see a request line and is
	/// otherwise simply dropped when the sign-in ends.
	///
	/// - Parameter connection: The connection the browser opened.
	/// - Returns: Nothing.
	private func accept(_ connection: NWConnection) {
		connection.start(queue: queue)
		connection.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, _, _ in
			guard let self, let data, let request = String(data: data, encoding: .utf8) else {
				connection.cancel()
				return
			}
			self.answer(request, on: connection)
		}
	}

	/// Answer one request, and record it when it is the redirect.
	///
	/// - Parameters:
	///   - request: The raw request the browser sent.
	///   - connection: The connection to answer on.
	/// - Returns: Nothing.
	private func answer(_ request: String, on connection: NWConnection) {
		guard
			let line = request.split(separator: "\r\n").first,
			let target = line.split(separator: " ").dropFirst().first,
			let components = URLComponents(string: "http://localhost\(target)")
		else {
			connection.cancel()
			return
		}

		guard components.path == wantedPath else {
			send(Page.stray, on: connection, status: "404 Not Found")
			return
		}

		let items = components.queryItems ?? []
		let caught = Redirect(
			code: items.first { $0.name == "code" }?.value ?? "",
			state: items.first { $0.name == "state" }?.value ?? "",
			error: items.first { $0.name == "error_description" }?.value
				?? items.first { $0.name == "error" }?.value ?? ""
		)
		send(caught.code.isEmpty || !caught.error.isEmpty ? Page.failed : Page.done, on: connection)

		// Recorded only once the page is on its way, so the caller can close the
		// port the moment it sees this without cutting the answer short.
		finish(.success(caught))
	}

	/// Send one HTML page and close the connection behind it.
	///
	/// - Parameters:
	///   - page: The page to send.
	///   - connection: The connection to send it on.
	///   - status: The status line to send it with.
	/// - Returns: Nothing.
	private func send(_ page: String, on connection: NWConnection, status: String = "200 OK") {
		let body = Data(page.utf8)
		let head = """
		HTTP/1.0 \(status)\r
		Content-Type: text/html; charset=utf-8\r
		Content-Length: \(body.count)\r
		Connection: close\r
		\r

		"""
		connection.send(content: Data(head.utf8) + body, completion: .contentProcessed { _ in
			connection.cancel()
		})
	}
}

/// The pages the browser is left looking at.
private enum Page {
	/// Return one page, in the style of the app rather than of a bare server.
	///
	/// - Parameters:
	///   - title: The heading.
	///   - detail: The line under it.
	/// - Returns: The whole document.
	static func make(title: String, detail: String) -> String {
		"""
		<!doctype html>
		<html lang="en"><head><meta charset="utf-8"><title>\(title)</title>
		<style>
		html{color-scheme:dark light}
		body{margin:0;min-height:100vh;display:grid;place-items:center;
		font:16px/1.5 -apple-system,system-ui,sans-serif}
		main{text-align:center;padding:2rem}
		h1{font-size:1.25rem;margin:0 0 .5rem}
		p{margin:0;opacity:.7}
		</style></head>
		<body><main><h1>\(title)</h1><p>\(detail)</p></main></body></html>
		"""
	}

	static let done = make(title: "Signed in", detail: "You can close this tab and go back to the app.")
	static let failed = make(title: "Sign-in was not completed", detail: "Go back to the app and try again.")
	static let stray = make(title: "Not here", detail: "This address is not part of signing in.")
}
