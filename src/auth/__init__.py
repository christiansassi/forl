"""The sign-in the widget performs for itself.

The widget used to borrow whatever token Claude Code or Codex had left on disk,
which meant it only worked on a machine with those tools installed and signed
in, and meant renewing a token the tool also owned. It now runs the login
itself: the OAuth authorization code flow with a proof key, against each
service's own endpoints, with the redirect caught on a loopback port this
process is listening on.

Nothing in here reads or writes the files those tools keep. The tokens go in the
widget's own file beside its preferences, so a machine with neither tool
installed still works, and a machine with both keeps them signed in.

The four parts are separate because they answer to different owners: `pkce` and
`jwt` are the token formats, `loopback` is the one request the browser makes
back to this process, `oauth` is the conversation with the provider, and `store`
is the file on disk.
"""
