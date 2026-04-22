# ProxyVault Client Mode Help

## Getting Started

If this is your first time opening ProxyVault, start with a single connection.

1. Add your config or subscription.
2. Select the entry in the list.
3. Click `Connect`.
4. If you want all system traffic to use it, click `Make Primary`.
5. Check the right panel for status, local ports, recent activity, and error guidance.

If you are unsure whether the connection really started, trust the runtime status first and the TCP check second.

## How the Connection Works

ProxyVault keeps the library entry separate from the live connection state.

That means:

- the library entry can exist even when nothing is running
- `Connect` starts a real local session
- a running session gets local HTTP and SOCKS ports
- the right panel reflects live runtime state rather than only a past network check

For normal proxy profiles, ProxyVault starts a local session and can optionally make it the primary system route.

For WireGuard profiles, the route is handled separately and may require system approval.
In a clean Windows release, WireGuard is provisioned through a bundled bootstrap payload: the system may ask only for UAC/network approval, not for a separate manual client installation.
On macOS, WireGuard and AmneziaWG still require platform tools such as `wg-quick` / `awg-quick`.

## What “Make Primary” Means

`Make Primary` means this active connection becomes the main system route for proxy traffic.

In practical terms:

- browsers and other apps start using this connection as the main system proxy
- only one proxy session can be primary at a time
- if the primary session stops or crashes, ProxyVault should clear the system proxy

Important: an active connection is not automatically the same as a primary connection.

You can keep a profile running locally without making it primary. That is useful when you want to use its local address manually in another app.

## What the Statuses Mean

Here is the user-facing meaning of the main statuses.

### Disconnected

The profile is in your library, but it is not running right now.

### Starting...

ProxyVault is preparing and launching the local session. If this state lasts too long, open the log.

### Connected

The session is running and ready to use through local ports.

### Primary

The session is running and is also selected as the main system proxy route.

### WireGuard Active

The connection is running through WireGuard and currently owns the route. In this mode, a normal system proxy should not pretend to be primary.

### Error

The session failed to start, exited too early, or lost its working state. Read the short explanation above the technical log.

## What the TCP Check Is

The TCP check answers a narrow question: can the app open a network connection to the server address and port.

That helps you quickly confirm:

- whether the server responds at all
- whether the address is blocked
- whether the port is correct

But the TCP check does not prove that the whole profile works. It does not replace a real launch, authentication, handshake, or system routing.

If the TCP check succeeds but the connection still does not start, the cause is usually in the profile parameters, the logs, or system permissions.

## What To Do If the Connection Does Not Start

Follow a simple order.

1. Make sure the config was pasted completely.
2. Compare the address, port, UUID, password, keys, and transport fields with the original source.
3. Check whether another app is already using the local port.
4. Read the short human explanation.
5. Then open the technical log.

Helpful interpretation of common problems:

- `Server is not responding`
  Usually a network, address, port, or remote-side issue.
- `Could not start the engine`
  Often caused by an invalid config, a missing runtime component, or a process that exits immediately.
- `Port is already in use`
  Two apps cannot listen on the same local port at the same time.
- `Authentication details were rejected`
  Review the username, password, UUID, public key, SNI, TLS, and transport settings.
- `Could not apply the system proxy`
  The local session may be up, but the operating system did not accept it as the primary route.
- `WireGuard needs confirmation`
  The system is asking for approval, elevation, or permission to change network settings.
- `Connection information is stale`
  The latest handshake or activity data is no longer fresh. Run the check again or reconnect.

## How To Tell Whether Your Mac Is Apple Silicon or Intel

1. Click the Apple icon in the top-left corner.
2. Open `About This Mac`.
3. Look at the `Chip` or `Processor` field.

How to read it:

- `Apple M1`, `Apple M2`, `Apple M3`, and similar names mean Apple Silicon
- `Intel` means an Intel Mac

Which archive to choose:

- Apple Silicon needs `arm64`
- Intel needs `x64`
- `universal2` works for both when available
