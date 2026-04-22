# Welcome to ProxyVault

## Short quick start

1. Add your connection.
2. Select it in the list.
3. Click `Connect`.
4. If needed, click `Make Primary`.
5. Check the status in the right panel.

## Extended version

ProxyVault helps you keep connections locally and start them without guesswork.

Begin with a single profile. That is enough to understand the full flow:

- add a URI, WireGuard config, or subscription
- select the entry in the library
- click `Connect`
- make it primary if needed
- if something goes wrong, read the short explanation first and open the technical log after that

Keep two important distinctions in mind:

- The TCP check helps confirm whether the server responds on the network, but it does not replace a real connection launch.
- WireGuard follows a separate route path and should not be treated like a normal system proxy session.

If you are moving a library to another machine, make sure you downloaded the archive that matches that system.
