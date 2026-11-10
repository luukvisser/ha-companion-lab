# Using the lab from a devcontainer (experimental)

**Experimental:** the relays have been tested with containers standing in for a devcontainer, not
with a real devcontainer (status at the end). Host networking (below) is the simple route.

A frontend repository's devcontainer (for example the Advanced Camera Card's) can drive the lab, so
an agent or Copilot working inside it can measure in the app. The lab's services listen on this
machine's loopback only (`adb` server 127.0.0.1:5037, the app's DevTools on `CDP_PORT`, the isolated
test Home Assistant on 127.0.0.1:8124), which a container cannot reach. Two ways:

- **Simplest (Linux):** run the devcontainer with host networking (`"runArgs": ["--network=host"]`
  in `devcontainer.json`). Inside it, `localhost:5037`, `localhost:9333` and `localhost:8124` are
  the lab's, exactly as on the host.
- **Without host networking:** `tools/devcontainer-bridge.sh up` starts small relays that listen
  on the Docker bridge address, accept connections only from the default bridge's subnet, and
  forward to the lab's loopback ports; the
  devcontainer adds `"runArgs": ["--add-host=host.docker.internal:host-gateway"]` and uses
  `host.docker.internal` with the relay ports it prints (Playwright:
  `android.devices({ host: 'host.docker.internal', port: <adb relay> })`; CDP:
  `http://host.docker.internal:<cdp relay>`; Home Assistant: `http://host.docker.internal:<ha relay>`).
  Any container on the default bridge can then reach these ports (the `adb` server has no login):
  stop the relays when done (`tools/devcontainer-bridge.sh down`).

A host firewall with an input policy of `drop` blocks containers on the bridge from reaching the
host: allow the relay ports from the Docker bridge interface, for example in nftables
`iifname "docker0" tcp dport { 15037, 19333, 18124 } accept`, or use host networking.

Status (10-11-2026): the relays start and listen on the bridge address. Binding alone did not keep
others out: a host on another network that routes to the bridge address reached a relay without
the source filter, and was refused with it (`range=`; tested with containers on two Docker
networks standing in for the bridge and a routed LAN peer). Connections from this machine itself
come from its LAN address and are refused too (use the loopback ports directly). On the test
machine its `drop` input policy blocked a bridge container, as expected (the rule above was not
added there), so a real devcontainer reaching a relay has not been run.
