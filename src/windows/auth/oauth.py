"""One OAuth client per provider, and the conversation held with it.

Both services accept the same flow, the authorization code flow with a proof
key that RFC 8252 defines for native applications, and differ only in their
addresses, their scopes and a handful of query parameters each wants. Those
differences are data, held in an OAuthClient, so the flow itself is written
once.

The client identifiers are not secrets. A public client cannot hold one, which
is the reason for the proof key, and both identifiers are shipped in the
command line tools these endpoints were built for.
"""

from __future__ import annotations

import sys
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from typing import Any, Callable

from ..usage.errors import CredentialsError, UsageAuthError
from ..usage.http import post_form
from ..validation import require_non_empty_str, require_number_in_range, require_type
from . import jwt, pkce, store
from .loopback import ANY_PORT, RedirectCatcher, port_is_free

# How long the user has to finish signing in. Long enough to cover a password
# manager, a second factor and a verification email.
SIGN_IN_TIMEOUT_SECONDS = 300.0

# A token this close to running out is renewed rather than used. Wide enough
# that a reading never starts with a token that expires while it is in flight.
RENEWAL_MARGIN_SECONDS = 600.0

ABANDONED_MESSAGE = "Sign-in was not completed."
EXPIRED_MESSAGE = "Sign-in expired."
NOT_SIGNED_IN_MESSAGE = "Not signed in."
REJECTED_MESSAGE = "The provider refused the sign-in."
WRONG_STATE_MESSAGE = "The sign-in answer did not match the request."


@dataclass(frozen=True)
class OAuthClient:
	"""Everything one provider's authorization flow needs.

	Attributes:
		key: Provider key, which is also the section of the credentials file the
			sign-in is stored in. str.
		label: Product name, used in what the user is told. str.
		authorize_url: Page the browser is sent to. str.
		token_url: Endpoint a code or a refresh token is exchanged at. str.
		client_id: The public identifier of this application. str.
		scope: Space separated scopes to ask for. str.
		redirect_port: Loopback port the redirect comes back to, which must be
			one the provider accepts for this client, or 0 when it accepts any
			and the system should pick one. int.
		redirect_path: Path of that redirect, such as "/callback". str.
		authorize_extras: Query parameters this provider wants on the
			authorization request and the other does not. tuple of str pairs.
		headers: Request headers this provider wants on a token request, such as
			the user agent an endpoint behind a bot check insists on. tuple of
			str pairs.
	"""

	key: str
	label: str
	authorize_url: str
	token_url: str
	client_id: str
	scope: str
	redirect_port: int
	redirect_path: str
	authorize_extras: tuple[tuple[str, str], ...] = ()
	headers: tuple[tuple[str, str], ...] = ()

	def redirect_uri(self, port: int) -> str:
		"""Return the redirect to name, for the port being listened on.

		Written with "localhost" rather than the address actually listened on,
		because that is the spelling the providers accept, and the exchange
		compares the two as text: the same string must go in both requests.

		Args:
			port: The port being listened on. int, 1 or more.

		Returns:
			str: The redirect URI.
		"""
		require_type(port, int, "port")
		if port < 1:
			raise ValueError("port must be 1 or more")
		return f"http://localhost:{port}{self.redirect_path}"


def authorization_url(client: OAuthClient, port: int, code_challenge: str, state: str) -> str:
	"""Return the page to send the browser to.

	Args:
		client: The provider's client. OAuthClient.
		port: The loopback port being listened on. int, 1 or more.
		code_challenge: The proof key challenge, as pkce.challenge returned it.
			str, non-empty.
		state: The value the provider must echo back. str, non-empty.

	Returns:
		str: The full authorization URL.
	"""
	require_type(client, OAuthClient, "client")
	require_non_empty_str(code_challenge, "code_challenge")
	require_non_empty_str(state, "state")

	# The extras go first, which is where the tool these endpoints were built
	# for puts the ones it sends. Order carries no meaning in a query string,
	# but an endpoint that answers "invalid request format" and nothing more
	# leaves no room to find out the hard way.
	fields = dict(client.authorize_extras)
	fields.update(
		{
			"client_id": client.client_id,
			"response_type": "code",
			"redirect_uri": client.redirect_uri(port),
			"scope": client.scope,
			"code_challenge": code_challenge,
			"code_challenge_method": "S256",
			"state": state,
		}
	)
	return f"{client.authorize_url}?{urllib.parse.urlencode(fields)}"


def _token_request(client: OAuthClient, fields: dict[str, str]) -> dict[str, Any]:
	"""Post to the token endpoint and return what it answers.

	The transport maps a refusal to the error a reading would raise, which is
	not what a refusal means here: a code this endpoint rejects is a sign-in
	that did not happen, not one that ran out. It is translated on the way out.

	Args:
		client: The provider's client. OAuthClient.
		fields: The form fields to send. dict of str to str.

	Returns:
		dict[str, Any]: The decoded answer.

	Raises:
		CredentialsError: When the endpoint refuses the request.
		UsageRequestError: When it cannot be reached.
	"""
	try:
		return post_form(client.token_url, fields, dict(client.headers))
	except UsageAuthError as exc:
		raise CredentialsError(REJECTED_MESSAGE) from exc


def exchange(client: OAuthClient, port: int, code: str, code_verifier: str, state: str) -> dict[str, Any]:
	"""Exchange an authorization code for tokens.

	The state goes with the exchange as well as with the authorization request,
	which is not what the specification asks for: state is meant to be the
	client's own business, checked when the redirect comes back. One of the two
	endpoints refuses the exchange outright without it, and the other ignores
	it, so it is always sent.

	Args:
		client: The provider's client. OAuthClient.
		port: The loopback port the authorization request named. int, 1 or more.
		code: The code the redirect carried. str, non-empty.
		code_verifier: The verifier whose challenge went with the authorization
			request. str, non-empty.
		state: The state that went with the authorization request. str,
			non-empty.

	Returns:
		dict[str, Any]: The token endpoint's answer, whose useful fields are
		access_token, refresh_token, expires_in and, for some providers,
		id_token.

	Raises:
		CredentialsError: When the endpoint refuses the code.
		UsageRequestError: When it cannot be reached.
	"""
	require_type(client, OAuthClient, "client")
	require_non_empty_str(code, "code")
	require_non_empty_str(code_verifier, "code_verifier")
	require_non_empty_str(state, "state")

	return _token_request(
		client,
		{
			"grant_type": "authorization_code",
			"code": code,
			"client_id": client.client_id,
			"redirect_uri": client.redirect_uri(port),
			"code_verifier": code_verifier,
			"state": state,
		},
	)


def renew(client: OAuthClient, refresh_token: str) -> dict[str, Any]:
	"""Exchange a refresh token for a new access token.

	Args:
		client: The provider's client. OAuthClient.
		refresh_token: The stored refresh token. str, non-empty.

	Returns:
		dict[str, Any]: The token endpoint's answer. Both providers retire the
		refresh token they are given and return a new one, so the caller must
		store the answer before using it.

	Raises:
		CredentialsError: When the endpoint refuses the refresh token, which
			means the sign-in must be done again.
		UsageRequestError: When it cannot be reached.
	"""
	require_type(client, OAuthClient, "client")
	require_non_empty_str(refresh_token, "refresh_token")

	return _token_request(
		client,
		{
			"grant_type": "refresh_token",
			"refresh_token": refresh_token,
			"client_id": client.client_id,
			"scope": client.scope,
		},
	)


def sign_in(
	client: OAuthClient,
	on_address: Callable[[str, bool], None],
	timeout: float = SIGN_IN_TIMEOUT_SECONDS,
) -> dict[str, Any]:
	"""Run the whole sign-in: open the browser, catch the code, exchange it.

	Blocks for as long as the user takes, so it belongs on a thread of its own
	rather than on the one drawing the interface.

	A browser that will not open is not the end of the attempt. The address is
	reported either way and the wait goes on, so whoever is watching can put it
	in front of the user to open by hand.

	Args:
		client: The provider's client. OAuthClient.
		on_address: Called once with the address to sign in at and whether a
			browser was opened at it. Callable taking one str and one bool and
			returning None.
		timeout: How long to wait for the browser to come back, in seconds.
			float, between 1 and 900.

	Returns:
		dict[str, Any]: The token endpoint's answer.

	Raises:
		CredentialsError: When the port is taken, the user did not finish, or
			the provider refused.
		UsageRequestError: When the token endpoint could not be reached.
	"""
	require_type(client, OAuthClient, "client")
	require_number_in_range(timeout, 1.0, 900.0, "timeout")
	if not callable(on_address):
		raise TypeError("on_address must be callable")

	if client.redirect_port != ANY_PORT and not port_is_free(client.redirect_port):
		# Only worth saying for a provider that accepts one port and no other.
		raise CredentialsError(
			f"Port {client.redirect_port} is in use, so {client.label} cannot sign in. "
			"Close whatever is using it and try again."
		)

	try:
		catcher = RedirectCatcher(client.redirect_port, client.redirect_path)
	except OSError as exc:
		raise CredentialsError(f"Cannot listen on port {client.redirect_port}: {exc}") from exc

	verifier = pkce.verifier()
	state = pkce.state()
	with catcher:
		port = catcher.port
		url = authorization_url(client, port, pkce.challenge(verifier), state)
		opened = webbrowser.open(url)
		if not opened:
			print(f"Open this address to sign in to {client.label}:\n{url}", file=sys.stderr)
		on_address(url, opened)
		redirect = catcher.wait(timeout)

	if redirect is None:
		raise CredentialsError(ABANDONED_MESSAGE)
	if redirect.error:
		print(f"{client.label} sign-in refused: {redirect.error}", file=sys.stderr)
		raise CredentialsError(REJECTED_MESSAGE)
	if redirect.state != state:
		raise CredentialsError(WRONG_STATE_MESSAGE)
	if not redirect.code:
		raise CredentialsError(ABANDONED_MESSAGE)
	return exchange(client, port, redirect.code, verifier, state)


def expires_at(answer: dict[str, Any]) -> float:
	"""Return when the access token in a token answer stops being accepted.

	Two providers say this two different ways. One returns the lifetime in
	seconds, the other returns a token that carries its own expiry, so both are
	tried before giving up and letting the endpoint be the judge.

	Args:
		answer: A token endpoint's answer. dict.

	Returns:
		float: The moment in seconds since the epoch, or 0.0 when nothing in the
		answer says.
	"""
	require_type(answer, dict, "answer")

	lifetime = answer.get("expires_in")
	if isinstance(lifetime, (int, float)) and lifetime > 0:
		return time.time() + float(lifetime)
	access = answer.get("access_token")
	return jwt.expiry(access) if isinstance(access, str) and access.strip() else 0.0


def usable(client: OAuthClient, margin: float = RENEWAL_MARGIN_SECONDS) -> store.Tokens:
	"""Return the stored sign-in, with an access token good for the next request.

	A token near its end is renewed here rather than at the endpoint's refusal,
	so a reading never starts with one that expires while it is in flight. The
	answer is written back before it is used: both providers retire the refresh
	token they are given, so one obtained and not stored is a sign-in lost.

	Args:
		client: The provider's client. OAuthClient.
		margin: How long before its expiry a token is renewed, in seconds.
			float, between 0 and 86400.

	Returns:
		store.Tokens: The sign-in, whose access token is current.

	Raises:
		CredentialsError: When nothing is stored, or the sign-in has run out and
			cannot be renewed.
		UsageRequestError: When the token endpoint could not be reached.
	"""
	require_type(client, OAuthClient, "client")
	require_number_in_range(margin, 0.0, 86400.0, "margin")

	tokens = store.load(client.key)
	if tokens is None:
		raise CredentialsError(NOT_SIGNED_IN_MESSAGE)
	if not tokens.expires_at or tokens.expires_at - time.time() >= margin:
		return tokens
	if not tokens.refresh_token.strip():
		raise CredentialsError(EXPIRED_MESSAGE)

	answer = renew(client, tokens.refresh_token)
	access = answer.get("access_token")
	if not isinstance(access, str) or not access.strip():
		raise CredentialsError(EXPIRED_MESSAGE)
	fresh = answer.get("refresh_token")
	return store.remember(
		client.key,
		tokens,
		access_token=access,
		refresh_token=fresh if isinstance(fresh, str) and fresh.strip() else tokens.refresh_token,
		expires_at=expires_at(answer),
	)
