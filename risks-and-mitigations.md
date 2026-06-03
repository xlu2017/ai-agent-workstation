# Risks and Mitigations

## Risk Matrix

| # | Risk | Likelihood | Impact | Severity | Mitigation |
|---|------|-----------|--------|----------|------------|
| 1 | DeepSeek API downtime/congestion | Medium | High | **High** | LiteLLM fallback to Qwen → Claude |
| 2 | DeepSeek geopolitical/regulatory risk | Low | Critical | **High** | Multi-provider setup; models are open-weight |
| 3 | Hetzner hardware failure | Low | High | **Medium** | RAID 1 + daily backups + documented rebuild |
| 4 | API pricing changes | Medium | Medium | **Medium** | Budget buffer; model alternatives pre-configured |
| 5 | OpenHands breaking update | Medium | Medium | **Medium** | Pin Docker image versions; test before upgrading |
| 6 | Disk failure (both NVMe) | Very Low | Critical | **Medium** | Off-site backups; RAID 1 protects against single drive |
| 7 | Network connectivity loss | Low | High | **Medium** | Tailscale maintains connection; server has 99.9% SLA |
| 8 | Exceeding $200/month budget | Low | Low | **Low** | DeepSeek costs are negligible; alerts at $150 |
| 9 | Security breach | Low | Critical | **High** | Tailscale + UFW + fail2ban + no public ports |
| 10 | Data loss | Low | Critical | **High** | Git (remote repos) + daily config backups |

---

## Detailed Risk Analysis

### Risk 1: DeepSeek API Downtime/Congestion

**Description:** DeepSeek has experienced service degradation during peak hours (especially during model launches or viral demand). The API may return 503 errors or have very high latency.

**Evidence:** DeepSeek experienced extended outages in January 2025 during the R1 launch. Peak-hour congestion remains documented in community reports.

**Mitigation:**
- LiteLLM configured with automatic fallback chain: DeepSeek → Qwen → Claude
- Fallback triggers on: timeout (30s), 5xx errors, rate limit (429)
- Qwen-turbo provides comparable code quality at similar cost
- Claude Haiku provides premium fallback at higher cost
- All fallbacks pre-tested and API keys pre-configured

**Residual risk:** Brief disruption during failover (seconds). Cost increase if running on Claude for extended periods.

---

### Risk 2: DeepSeek Geopolitical/Regulatory Risk

**Description:** DeepSeek is a Chinese company. Potential risks include: US government restrictions on Chinese AI services, data sovereignty concerns, service discontinuation for non-Chinese users.

**Mitigation:**
- DeepSeek V4 models are **open-weight** (MIT license) — can self-host if API becomes unavailable
- Qwen models (Alibaba) are also open-weight
- SiliconFlow provides alternative hosting for same models
- LiteLLM makes provider switching a config change (no code changes)
- No proprietary/sensitive code sent to any single provider exclusively
- If self-hosting becomes necessary: RunPod/Vast.ai for inference (Qwen 32B fits on RTX 4090)

**Residual risk:** If both DeepSeek AND Alibaba services are blocked simultaneously, would need to self-host or switch to Western providers (significant cost increase).

---

### Risk 3: Hetzner Hardware Failure

**Description:** Dedicated server hardware can fail (disk, RAM, CPU, PSU). Hetzner provides replacement but requires downtime.

**Mitigation:**
- Software RAID 1: Protects against single disk failure (no data loss, no downtime)
- Daily backups of `/home/agent/ai-workstation/` to Hetzner Storage Box (~$4/mo for 1TB)
- Git repositories stored on GitHub (always recoverable)
- Documented rebuild procedure: full stack can be reproduced from `setup.sh` in <2 hours
- Hetzner provides hardware replacement within 24 hours (SLA)

**Residual risk:** 4–24 hours downtime for catastrophic hardware failure (motherboard, etc.). Acceptable given "no 100% uptime" constraint.

---

### Risk 4: API Pricing Changes

**Description:** Model providers may increase prices. DeepSeek has historically decreased prices, but this is not guaranteed.

**Mitigation:**
- Current cost is ~$10–35/month for API — even a 5× increase keeps total under $200
- Budget has $105–136 buffer at moderate usage
- LiteLLM allows instant switching between equivalent models
- Open-weight models can be self-hosted on RunPod if API prices become unreasonable
- Multiple providers pre-configured: price competition keeps market honest

**Residual risk:** Minimal. Would need >10× price increase to threaten budget.

---

### Risk 5: OpenHands Breaking Update

**Description:** OpenHands is actively developed. Docker image updates may introduce breaking changes, new dependencies, or incompatibilities.

**Mitigation:**
- Pin Docker image to specific version tag (e.g., `ghcr.io/all-hands-ai/openhands:0.40.0`)
- Test updates in separate Docker instance before replacing production
- Keep `docker-compose.yml` in git — can roll back instantly
- Monitor OpenHands GitHub releases and changelogs before updating

**Residual risk:** Manual update process required. Automated updates disabled.

---

### Risk 6: Catastrophic Disk Failure (Both NVMe)

**Description:** Both NVMe drives in RAID 1 fail simultaneously (extremely rare but possible with power surge, controller failure, or same-batch manufacturing defect).

**Mitigation:**
- Daily off-site backups (Hetzner Storage Box or rsync to cloud)
- All code stored in remote Git repositories (GitHub)
- Infrastructure-as-code: `setup.sh` + `docker-compose.yml` enables full rebuild
- Configuration files backed up daily
- Recovery procedure documented in `backup.md`

**Residual risk:** Loss of up to 24 hours of non-committed work. Acceptable.

---

### Risk 7: Network Connectivity Loss

**Description:** Hetzner network outage, ISP issues, or DDoS attack making server unreachable.

**Mitigation:**
- Hetzner guarantees 99.9% network availability (SLA)
- DDoS protection included with dedicated servers
- Tailscale provides redundant connectivity path
- Agent sessions continue running locally during brief outages
- No business-critical real-time requirement (async development workflow)

**Residual risk:** Minimal. Historical Hetzner uptime exceeds 99.95%.

---

### Risk 8: Budget Overrun

**Description:** Unexpected costs push monthly bill above $200.

**Mitigation:**
- DeepSeek V4-Flash at $0.14/$0.28 per 1M tokens makes cost overrun nearly impossible from API usage alone
- Set up LiteLLM budget alerts at $50, $100, $150 API spend
- Infrastructure cost is fixed ($59/mo) — no variable charges
- Traffic is unlimited (no bandwidth overage)
- No stopped-instance billing surprises (dedicated = always billed same amount)

**Residual risk:** Effectively zero with current pricing structure.

---

### Risk 9: Security Breach

**Description:** Unauthorized access to the server, exposed API keys, or compromised agent sandboxes.

**Mitigation:**
- **Network:** Tailscale-only access; UFW blocks all public ports except SSH
- **Authentication:** SSH key-only (no password); fail2ban for brute-force protection
- **Secrets:** Stored in `.env` files with 600 permissions; never committed to git
- **Docker:** Agent sandboxes are isolated containers; no host filesystem access beyond mounted volumes
- **Updates:** Unattended security updates enabled
- **API keys:** Rotatable; LiteLLM master key protects proxy access
- **Monitoring:** Login notifications via `pam_exec` or similar

**Residual risk:** Low. Standard Linux hardening practices applied.

---

### Risk 10: Data Loss

**Description:** Loss of code, configurations, or agent session history.

**Mitigation:**
- All code pushed to GitHub (distributed backup inherent in Git)
- Configuration in version-controlled `ai-workstation/` directory
- Daily automated backup of non-git data
- Docker volumes backed up via script
- RAID 1 protects against single-disk failure

**Residual risk:** Minimal. Git is inherently distributed; worst case = loss of uncommitted changes.

---

## Contingency Plans

### If DeepSeek becomes permanently unavailable:

1. Immediate: LiteLLM auto-fails over to Qwen (no action needed)
2. Short-term: Increase Qwen/SiliconFlow usage ($5–15/mo)
3. Medium-term: Self-host Qwen3 32B on RunPod ($0.69/hr when needed)
4. Long-term: Evaluate Gemini Flash or GPT-4.1-mini as primary

### If Hetzner server has catastrophic failure:

1. Order new server or spin up CCX33 cloud instance (30 seconds)
2. Run `setup.sh` on new instance (~30 min)
3. Restore configs from backup
4. Resume operations

### If budget needs to decrease below $60/mo:

1. Downgrade to Hetzner Cloud CPX52 (16 shared vCPU, 32GB): $42.99/mo
2. Or downgrade to CPX42 (8 shared vCPU, 16GB): $29.99/mo
3. Keep DeepSeek V4-Flash as primary (API costs stay <$10/mo)
4. Total: $40–53/mo

### If we need to scale UP beyond AX42-U:

1. Upgrade path: AX102-U (16c/128GB) at ~$113/mo
2. Or add Hetzner Cloud instances for parallel sandboxes
3. Or add RunPod GPU workers for ML tasks
4. Budget allows up to $200/mo — plenty of room for expansion

---

## Decision Log

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Hetzner dedicated over cloud | Better value, bare-metal perf, unlimited traffic | Cloud CCX33 (instant provisioning, $15 more) |
| AX42-U over AX41 | Zen 4 architecture, DDR5, Gen4 NVMe worth $17/mo premium | AX41 (cheaper but Zen 2, DDR4) |
| Finland location | Good latency to both EU and Asia (DeepSeek) | Germany (slightly better EU latency) |
| DeepSeek over self-hosted | 50-100× cheaper than equivalent compute; no GPU needed | Self-hosted Qwen on GPU ($500+/mo) |
| LiteLLM over direct API | Unified interface, fallbacks, cost tracking | Direct API calls (simpler but no failover) |
| Tailscale over public HTTPS | Zero-config security, no certificates to manage | Caddy + Let's Encrypt (more complex) |
| Docker Compose over K8s | Appropriate complexity for single-server setup | Kubernetes (overkill) |
| RAID 1 over RAID 0 | Data integrity over speed; NVMe already fast enough | RAID 0 (2× capacity but no redundancy) |
