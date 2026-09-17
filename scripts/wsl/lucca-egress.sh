#!/bin/bash
# Project Lucca — Sandbox Egress Policy Setup (ADR-003, Spec 09 §8)
# Sets up LUCCA-EGRESS chain on DOCKER-USER in Ubuntu WSL2
set -euo pipefail

# Ensure lucca-net network exists
if ! docker network inspect lucca-net >/dev/null 2>&1; then
  docker network create \
    --subnet 172.28.0.0/24 \
    --opt com.docker.network.bridge.enable_ip_masquerade=true \
    --opt enable_ipv6=false \
    lucca-net
fi

# Disable IPv6 system-wide in WSL
sysctl -w net.ipv6.conf.all.disable_ipv6=1 >/dev/null 2>&1 || true

# Idempotent: create or flush LUCCA-EGRESS chain
iptables -N LUCCA-EGRESS 2>/dev/null || iptables -F LUCCA-EGRESS
iptables -D DOCKER-USER -s 172.28.0.0/24 -j LUCCA-EGRESS 2>/dev/null || true
iptables -I DOCKER-USER 1 -s 172.28.0.0/24 -j LUCCA-EGRESS

# 1. Allow replies to established/related flows
iptables -A LUCCA-EGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# 2. Block private/local/special networks BEFORE web allow
for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10 \
           127.0.0.0/8 224.0.0.0/4 240.0.0.0/4 0.0.0.0/8; do
  iptables -A LUCCA-EGRESS -d "$net" -j REJECT --reject-with icmp-admin-prohibited
done

# 3. Allow public HTTP and HTTPS only
iptables -A LUCCA-EGRESS -p tcp -m multiport --dports 80,443 -j ACCEPT

# 4. Allow DNS queries to pinned Cloudflare upstreams only (ADR-003 §3)
iptables -A LUCCA-EGRESS -p udp -d 1.1.1.1 --dport 53 -j ACCEPT
iptables -A LUCCA-EGRESS -p udp -d 1.0.0.1 --dport 53 -j ACCEPT
iptables -A LUCCA-EGRESS -p tcp -d 1.1.1.1 --dport 53 -j ACCEPT
iptables -A LUCCA-EGRESS -p tcp -d 1.0.0.1 --dport 53 -j ACCEPT

# 4. Default DROP with rate-limited logging
iptables -A LUCCA-EGRESS -m limit --limit 5/min -j LOG --log-prefix "LUCCA-EGRESS-DROP " 2>/dev/null || true
iptables -A LUCCA-EGRESS -j DROP

echo "LUCCA-EGRESS rules configured successfully."
