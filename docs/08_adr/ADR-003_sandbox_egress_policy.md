# ADR-003 — Sandbox Egress: Docker CE in Ubuntu WSL2, ordered `DOCKER-USER` allow-list with default DROP, IPv6 disabled

**Status:** Accepted 2026-09-17 (D-03, D-04)
**Supersedes:** doc 03 L202–210 and doc 01 L124–130 iptables blocks (both wrong, both different).

## Context

Two rulesets existed. Both insert with `-I`, which **prepends**, so the last-written ACCEPT lines end up evaluated first; a container could reach `192.168.1.1:443` or send DNS to any LAN resolver. Neither had a terminal DROP, so any port other than 80/443/53 to the public internet was open. `172.28.0.0/16` (the Lucca bridge) sits inside `172.16.0.0/12`, so the REJECT for that range also matched the bridge itself. IPv6 was unaddressed. Rules were not persisted across `wsl --shutdown`. The egress test (`curl` fails) was vacuous. Docker Desktop was implicitly assumed but ignores Ubuntu's iptables entirely (research 7.4).

## Decision

1. **Docker CE** installed inside the Ubuntu WSL2 distro (`apt install docker-ce`), `iptables` legacy or nft backend consistently (pin one), WSL `networkingMode=nat`.
2. Dedicated bridge network `lucca-net` `172.28.0.0/24`, `--internal` **not** used (web tool needs egress), `com.docker.network.bridge.enable_ip_masquerade=true`, `enable_ipv6=false`. Sysctl inside WSL: `net.ipv6.conf.all.disable_ipv6=1`.
3. Rules appended (`-A`) in this exact order to `DOCKER-USER`, source-scoped to the bridge:

```bash
# scripts/wsl/lucca-egress.sh  (idempotent: flush our chain first)
iptables -N LUCCA-EGRESS 2>/dev/null || iptables -F LUCCA-EGRESS
iptables -D DOCKER-USER -s 172.28.0.0/24 -j LUCCA-EGRESS 2>/dev/null
iptables -I DOCKER-USER 1 -s 172.28.0.0/24 -j LUCCA-EGRESS

# 1. replies to established flows
iptables -A LUCCA-EGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
# 2. (no DNS rule needed here — see "DNS path" below; direct :53 from a container falls through to REJECT/DROP)
# 3. block everything private / local / special BEFORE any web allow
for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10 \
           127.0.0.0/8 224.0.0.0/4 240.0.0.0/4 0.0.0.0/8; do
  iptables -A LUCCA-EGRESS -d "$net" -j REJECT --reject-with icmp-admin-prohibited
done
# 4. public web only
iptables -A LUCCA-EGRESS -p tcp -m multiport --dports 80,443 -j ACCEPT
# 5. default deny (logged, rate-limited)
iptables -A LUCCA-EGRESS -m limit --limit 5/min -j LOG --log-prefix "LUCCA-EGRESS-DROP "
iptables -A LUCCA-EGRESS -j DROP
```

   **DNS path (normative).** Containers on a user-defined network resolve via Docker's embedded resolver (`127.0.0.11` inside the container netns). `dockerd` answers those queries **from the host network namespace**, so they never traverse `FORWARD`/`DOCKER-USER` and cannot be filtered there. Therefore:
   - `/etc/docker/daemon.json` pins the upstream: `{"dns": ["1.1.1.1", "1.0.0.1"], "dns-search": []}` — the embedded resolver can only ever forward to Cloudflare, never to a LAN resolver.
   - Any process that bypasses the embedded resolver and sends UDP/TCP `:53` directly to a LAN IP hits the RFC1918 REJECT; directly to a public IP hits the final DROP (only 80/443 are allowed). Verified by **T-SBX-07** (`dig @192.168.1.1` blocked; `dig example.com` via embedded resolver works).
   - Residual: DNS tunnelling through the embedded resolver to 1.1.1.1 remains possible in principle. The web-sandbox has no files, and LLM-carried exfiltration is limited by the risk policy (ADR-004 §residual). Accepted; revisit with the egress-proxy alternative in Phase 7.
4. Persistence: the script runs from `/etc/wsl.conf` `[boot] command=` and again from `lucca-core` startup (idempotent) after `docker network inspect lucca-net` succeeds.
5. **Verification is positive-controlled** (spec 09 / matrix): start `python -m http.server 8089` bound to the Windows LAN IP; assert reachable from Ubuntu shell; assert **unreachable** from the container (`exit 7` or `28`, under 3 s); assert `https://example.com` reachable; assert `nc -zv 1.1.1.1 22` blocked; assert IPv6 `curl -6` fails with "network unreachable".

## Consequences

- Sandbox web fetch can reach the public internet on 80/443 only; nothing on the LAN, host, or link-local is reachable.
- Docker Desktop is unsupported; documented in the install guide.
- Rules must be re-applied after WSL restarts — handled by boot command + startup idempotence.
- The DNS path ambiguity is explicitly a test, not an assumption.

## Alternatives

| Option | Why not (now) |
|---|---|
| `--network internal` + egress proxy container (allow-list HTTP proxy) | Cleaner trust boundary; adds a container (~50 MB) and proxy config. **Recommended upgrade in Phase 7 if the fetch tool's allow-list grows.** |
| gVisor (`runsc`) runtime | Stronger syscall isolation; not available in WSL2 kernel without custom build. Phase 7+ consideration. |
| Firecracker / E2B-style microVMs | No nested virt story inside WSL2 that is worth the complexity for a single-user desktop. |
