"""English human-readable error glossary for runtime surfaces."""

ERROR_GLOSSARY_EN: dict[str, dict[str, str]] = {
    "server_unreachable": {
        "title": "Server is not responding",
        "summary": "The app could not reach the remote address or port.",
        "next_step": "Check the address, port, internet access, and whether the server is reachable.",
    },
    "engine_failed_to_start": {
        "title": "Could not start the engine",
        "summary": "The local process did not start correctly or exited immediately.",
        "next_step": "Review the config, confirm runtime components are present, and open the technical log.",
    },
    "port_in_use": {
        "title": "Port is already in use",
        "summary": "The required local port is already being used by another app.",
        "next_step": "Close the conflicting app or choose another local port.",
    },
    "authentication_failed": {
        "title": "Authentication details were rejected",
        "summary": "The server rejected the username, password, UUID, key, or another access parameter.",
        "next_step": "Compare the values with the original config and try again.",
    },
    "system_proxy_apply_failed": {
        "title": "Could not apply the system proxy",
        "summary": "The local session may be running, but the operating system did not accept it as the primary route.",
        "next_step": "Check app permissions, review system settings, and try `Make Primary` again.",
    },
    "wireguard_confirmation_required": {
        "title": "WireGuard needs confirmation",
        "summary": "The operating system is asking for permission to change network settings or start a helper component.",
        "next_step": "Approve the system prompt and retry the connection if needed.",
    },
    "system_conflict": {
        "title": "A system networking component is conflicting",
        "summary": "The AmneziaWG check is being interrupted by another system service or helper that already owns the required resource.",
        "next_step": "Review competing Amnezia/AmneziaWG services, disable the conflicting split-tunnel helper, and run the check again.",
    },
    "runtime_component_missing": {
        "title": "A required runtime component is missing",
        "summary": "The specific configuration cannot be verified or launched because the platform-level client or helper component is not available on this device.",
        "next_step": "On Windows, confirm the bundled release is complete. On macOS, install the required `wg-quick` or `awg-quick` tools and try again.",
    },
    "runtime_bundle_incomplete": {
        "title": "The build is incomplete",
        "summary": "This release is missing a bundled runtime payload, or the shipped checksum no longer matches the pinned expectation.",
        "next_step": "Use a complete ProxyVault release or rebuild it with the pinned WireGuard bootstrap payload and the runtime notice bundle.",
    },
    "invalid_configuration": {
        "title": "The configuration is incomplete or damaged",
        "summary": "The profile failed local validation because required fields are missing or the format could not be parsed.",
        "next_step": "Review the [Interface]/[Peer] blocks, keys, and endpoint, then import the configuration again.",
    },
    "handshake_missing": {
        "title": "No handshake was observed",
        "summary": "The tunnel started, but the runtime did not observe a server handshake during the check window.",
        "next_step": "Check the keys, endpoint, and server reachability, then retry after sending traffic through the tunnel.",
    },
    "handshake_stale": {
        "title": "Connection information is stale",
        "summary": "The latest handshake or activity data is no longer considered fresh.",
        "next_step": "Run the check again or reconnect the profile.",
    },
}
