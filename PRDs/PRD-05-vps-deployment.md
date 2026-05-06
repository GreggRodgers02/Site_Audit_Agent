# PRD-05: VPS Deployment on Hostinger
**Site Audit Agent — Sherwin-Williams PCG Asset Protection**

---

**Document Version:** 1.0
**Date:** 2026-05-05
**Author:** PM Agent (claude-sonnet-4-6)
**PRD ID:** PRD-05
**Status:** Draft — Pending Engineering Review
**Depends On:** PRD-01 through PRD-04 (application must be complete before deployment)

---

## 1. Overview

PRD-05 defines all requirements necessary to deploy the Site Audit Agent to a Hostinger VPS so that every APM can access it through a standard web browser without any local setup. This PRD covers infrastructure provisioning, process management, reverse proxy configuration, SSL termination, and supporting documentation for a non-developer IT administrator to execute the deployment end-to-end.

---

## 2. Problem Statement

### Current State
The application runs on a single developer's local machine. APMs who need to generate reports must either wait for the developer or attempt local setup — requiring Python environment setup, dependency installation, and API key management.

### Desired State
Any APM with network access opens a browser, navigates to a stable URL, and uses the Site Audit Agent without installing anything locally. The application runs continuously, restarts automatically on failure, and is served over HTTPS.

---

## 3. Goals and Objectives

### Primary Goal
Deploy the Site Audit Agent to a Hostinger Ubuntu 22.04 VPS such that all APMs can access it via browser over HTTPS with no local setup required.

### Secondary Goals
- App auto-recovers from crashes without manual intervention
- Clear deployment guide for IT admin with Linux SSH access
- Repeatable, scriptable deployment process for future updates
- OpenAI API key and secrets kept out of source control

### Non-Goals
- User authentication / SSO
- Docker / Kubernetes containerization
- CI/CD pipelines or automated deployment on git push
- Database backups or data persistence strategy
- Horizontal scaling or load balancing
- Monitoring, alerting, or log aggregation beyond systemd journal
- Application-level feature changes

---

## 4. Target Users

### Primary: IT Administrator / DevOps
Technically proficient, SSH access with sudo, comfortable with Linux CLI. Not necessarily a developer. Needs single setup script and clear documentation for manual steps.

Pain points: WeasyPrint system deps are non-obvious; Streamlit WebSocket requirements cause silent failures in naive Nginx configs; secrets management without a secrets manager requires careful handling.

### Secondary: APM (Asset Protection Manager)
Non-technical. Accesses via browser on laptop or tablet. Needs a stable HTTPS URL. No installation, no CLI, no API keys.

---

## 5. Proposed Solution

### Architecture

```
APM Browser
     |
     | HTTPS (port 443)
     ↓
[Nginx Reverse Proxy]
     |
     | HTTP (port 8501, localhost only)
     ↓
[Streamlit App Process]  ← managed by systemd
     |
     ↓
[SQLite DB]  [OpenAI API]  [WeasyPrint (PDF)]
```

Nginx terminates SSL (Let's Encrypt / Certbot) and proxies requests — including WebSocket upgrade headers — to Streamlit on localhost:8501. Streamlit is managed as a systemd service (starts on boot, restarts on crash). `.env` file supplies the OpenAI API key at runtime.

### Deliverables

| File | Purpose |
|---|---|
| `deploy/nginx.conf` | Nginx server block — reverse proxy with SSL, WebSocket support |
| `deploy/site-audit-agent.service` | systemd unit file — process management and `.env` loading |
| `deploy/setup.sh` | Automated server provisioning script |
| `deploy/README.md` | Step-by-step deployment guide for IT admin |

---

## 6. Functional Requirements

### FR-01: Nginx Reverse Proxy

- Listen on port 80 → redirect all HTTP traffic to HTTPS (301)
- Listen on port 443 with TLS (Let's Encrypt certificates)
- Proxy all requests to `http://127.0.0.1:8501`
- Required headers for Streamlit WebSocket support:
  - `Upgrade: $http_upgrade`
  - `Connection: "upgrade"`
  - `Host: $host`
  - `X-Real-IP: $remote_addr`
  - `X-Forwarded-For: $proxy_add_x_forwarded_for`
  - `X-Forwarded-Proto: $scheme`
- `proxy_buffering off` (no WebSocket frame buffering)
- `proxy_read_timeout` minimum 300 seconds (long report generation)
- Accept both `www.` and bare domain, or configurable for IP-only

### FR-02: systemd Service Unit

- Execute `streamlit run app.py` from the application's working directory
- Run as non-root user (configurable, default: SSH deploy user)
- `Restart=always`, `RestartSec` >= 5 seconds
- Load env from `/srv/site-audit-agent/.env` via `EnvironmentFile=`
- `After=network.target`, `WantedBy=multi-user.target`
- Streamlit binds to `127.0.0.1:8501` only (not publicly exposed)
- stdout/stderr to systemd journal (accessible via `journalctl -u site-audit-agent`)

### FR-03: Automated Setup Script

`setup.sh` must perform the following in order with clear echo output:

1. `apt-get update`
2. Install Python 3.11+, `python3-pip`, `python3-venv`
3. Install WeasyPrint system deps (see Section 7.4)
4. Install Nginx
5. Install Certbot and `python3-certbot-nginx` plugin
6. Clone repo to `/srv/site-audit-agent/`
7. Create venv at `/srv/site-audit-agent/venv/`
8. Install Python deps from `requirements.txt` into venv
9. Copy service file to `/etc/systemd/system/`
10. `systemctl daemon-reload`, `enable site-audit-agent`, `start site-audit-agent`
11. Copy `nginx.conf` to `/etc/nginx/sites-available/site-audit-agent`, create symlink in `sites-enabled/`
12. Remove default Nginx site symlink if present
13. `nginx -t` (test config) and `systemctl reload nginx`
14. Print reminder to: (a) create `.env` at `/srv/site-audit-agent/.env`, (b) run Certbot with domain name

Script requirements:
- Idempotent where possible (`git pull` instead of re-cloning if dir exists)
- `set -e` (exit immediately on error)
- `chmod +x deploy/setup.sh`
- No interactive input except steps that are inherently interactive (Certbot domain validation)

### FR-04: Deployment README

`deploy/README.md` must include:

1. **Prerequisites checklist** — SSH access, sudo, domain pointed at VPS IP, GitHub access, OpenAI API key
2. **Step-by-step instructions** — exact copy-pasteable commands in correct order
3. **`.env` file format** — exact variable names and format
4. **Certbot command** — exact `certbot --nginx -d yourdomain.com` with placeholder instructions
5. **Service management commands** — check status, view logs, restart, stop
6. **Updating the application** — `git pull` → `pip install` → `systemctl restart`
7. **Troubleshooting section** — diagnosis for:
   - Streamlit port not listening (service not started)
   - 502 Bad Gateway (proxy misconfiguration or service crash)
   - WeasyPrint import errors (missing system dependencies)
   - SSL certificate errors (Certbot not run or cert expired)
   - WebSocket connection failures (missing Nginx upgrade headers)

---

## 7. Technical Specifications

### 7.1 Server Environment

| Parameter | Value |
|---|---|
| OS | Ubuntu 22.04 LTS |
| Python Version | 3.11+ |
| Web Server | Nginx (latest stable from apt) |
| Process Manager | systemd |
| SSL Provider | Let's Encrypt via Certbot |
| App Working Directory | `/srv/site-audit-agent/` |
| Virtual Environment | `/srv/site-audit-agent/venv/` |
| Service Name | `site-audit-agent` |
| Streamlit Bind Address | `127.0.0.1:8501` |
| Nginx Config Path | `/etc/nginx/sites-available/site-audit-agent` |
| systemd Unit Path | `/etc/systemd/system/site-audit-agent.service` |
| Environment File Path | `/srv/site-audit-agent/.env` |

### 7.2 Nginx Configuration Notes

- `proxy_http_version 1.1` required for `Upgrade` header / WebSocket support (Streamlit real-time UI)
- SSL block must be compatible with Certbot's `--nginx` injection (no pre-configured `ssl_certificate` conflicting with Certbot)

### 7.3 systemd EnvironmentFile Format

Simple `KEY=VALUE` format — no `export` statements (systemd does not process shell syntax):

```
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

### 7.4 WeasyPrint System Dependencies (Ubuntu 22.04)

```
libpango-1.0-0
libpangoft2-1.0-0
libpangocairo-1.0-0
libcairo2
libgdk-pixbuf2.0-0
libffi-dev
libxml2-dev
libxslt1-dev
shared-mime-info
fonts-liberation
```

Install BEFORE `pip install -r requirements.txt` to avoid WeasyPrint post-install import errors.

### 7.5 Streamlit Configuration

Set in `~/.streamlit/config.toml` on server or as CLI flags in systemd `ExecStart`:

```toml
[server]
headless = true
port = 8501
address = "127.0.0.1"
enableCORS = false
enableXsrfProtection = false
```

`enableCORS = false` and `enableXsrfProtection = false` required when Streamlit sits behind Nginx proxy.

### 7.6 Security Considerations

- `.env` owned by deploy user, mode `600` (`chmod 600 .env`) — enforced by setup script
- VPS firewall (UFW): only ports 22, 80, 443 open; port 8501 blocked externally
- SSH key-based auth assumed; README notes to disable password-based SSH

### 7.7 File and Directory Permissions

| Path | Owner | Mode |
|---|---|---|
| `/srv/site-audit-agent/` | deploy user | `755` |
| `/srv/site-audit-agent/.env` | deploy user | `600` |
| `/srv/site-audit-agent/venv/` | deploy user | `755` |
| `/etc/systemd/system/site-audit-agent.service` | root | `644` |
| `/etc/nginx/sites-available/site-audit-agent` | root | `644` |

---

## 8. User Stories

**US-001 — Automated system dependency installation**
Given a fresh Ubuntu 22.04 VPS with SSH and sudo, when admin runs `sudo bash deploy/setup.sh`, then Python 3.11+, pip, venv, Nginx, Certbot, and all WeasyPrint system deps install without error. `python3 -c "import weasyprint"` raises no ImportError.

**US-002 — Repo clone and Python environment setup**
Repo cloned to `/srv/site-audit-agent/`. Venv created and `requirements.txt` installed. Re-running script uses `git pull` instead of failing on existing directory.

**US-003 — systemd service for auto-start and auto-restart**
After reboot, `systemctl status site-audit-agent` shows `active (running)` within 30 seconds. After manual kill, service auto-restarts within 5 seconds. `OPENAI_API_KEY` available to process from `.env`.

**US-004 — Secrets loaded from .env — never from source control**
No secrets in any committed file. `.env` in `.gitignore`. Service unit references `EnvironmentFile` only. `.env` on server has permissions `600`.

**US-005 — Nginx reverse proxy with WebSocket support**
Navigating to server address redirects HTTP → HTTPS. Streamlit UI renders without "Unable to connect" errors. WebSocket connections stable during report generation. `nginx -t` passes.

**US-006 — HTTPS via Let's Encrypt**
Following README Certbot command issues valid certificate. Browser shows valid padlock. `curl -I https://<domain>` returns 200 with no SSL errors. `systemctl status certbot.timer` shows active auto-renewal.

**US-007 — Step-by-step deployment guide**
IT admin following `deploy/README.md` from beginning deploys successfully in one session. Every command is complete and copy-pasteable. Troubleshooting section covers 502 Bad Gateway with specific diagnostic command.

**US-008 — Application update procedure**
README "Updating the Application" section includes in order: `git pull`, `pip install -r requirements.txt` (in venv), `systemctl restart site-audit-agent`. After restart, service shows `active (running)` within 15 seconds.

**US-009 — UFW firewall restricts to required ports only**
Setup script applies `ufw allow 22/80/443` and `ufw enable`. Direct connection to `:8501` is refused. `ufw status` lists only 22, 80, 443 as ALLOW.

---

## 9. Acceptance Criteria

### Functional Acceptance
- [ ] `setup.sh` runs to completion on fresh Ubuntu 22.04 VPS without manual intervention (excluding `.env` creation and Certbot domain validation)
- [ ] `systemctl status site-audit-agent` shows `active (running)` after setup
- [ ] `systemctl status site-audit-agent` shows `active (running)` after server reboot
- [ ] Service auto-restarts within 10 seconds after manual process kill
- [ ] Browser loads Streamlit UI at server domain/IP without error
- [ ] HTTP traffic automatically redirected to HTTPS
- [ ] Valid SSL certificate (no browser warnings) when domain used and Certbot run
- [ ] WebSocket connections stable during interactive UI use and report generation
- [ ] Full report generated end-to-end (including WeasyPrint PDF) from deployed browser session
- [ ] Port 8501 not accessible from outside the server

### Documentation Acceptance
- [ ] `deploy/README.md` contains all sections specified in FR-04
- [ ] IT admin with no Python background can complete deployment successfully following README only
- [ ] All commands in README are complete and copy-pasteable
- [ ] Troubleshooting section addresses all five failure modes in FR-04

### Security Acceptance
- [ ] `.env` not committed to git repository
- [ ] `.env` listed in `.gitignore`
- [ ] `.env` on server has permissions `600`
- [ ] No API keys or secrets in any committed file
- [ ] UFW enabled with port 8501 blocked from external access

---

## 10. Out of Scope

| Item | Rationale |
|---|---|
| User authentication | Separate PRD; tool is internal-network access only currently |
| Docker / containerization | Operational overhead not warranted for single-instance internal tool |
| CI/CD pipeline | Manual SSH deployment sufficient for team size and release cadence |
| Database backups | Data management PRD |
| Log aggregation | `journalctl` sufficient for current operational maturity |
| Horizontal scaling | Single VPS appropriate for APM team usage volume |
| Custom Nginx error pages | Infrastructure polish future PRD |
| Application-level feature changes | Strictly infrastructure and deployment |
| Windows or macOS server targets | Ubuntu 22.04 LTS only |

---

## 11. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| WeasyPrint system deps incomplete on Ubuntu 22.04 | Medium | High | Validate full dep list via clean-room test deployment before handoff; pin WeasyPrint version in `requirements.txt` |
| Domain not pointed at VPS IP before Certbot run | High | Medium | README pre-flight steps to verify DNS resolution; document IP-only (HTTP) fallback |
| Streamlit WebSocket drops through Nginx (missing headers) | Medium | High | `nginx.conf` pre-configured with all required headers; WebSocket stability in acceptance test |
| `.env` accidentally committed to git | Low | Critical | `.env` in `.gitignore` from PRD-01; README explicit warning |
| Setup script not idempotent on re-run | Medium | Medium | Conditional logic checks for existing dirs before cloning |
| Hostinger provider-level firewall conflicts with UFW | Low | Medium | README note to check Hostinger control panel firewall settings |

---

## 12. Dependencies & Prerequisites

### Must be satisfied before deployment begins:

- [ ] Hostinger VPS provisioned, running Ubuntu 22.04 LTS
- [ ] VPS has at least 1 GB RAM and 20 GB disk
- [ ] SSH access with sudo privileges for the deploying admin
- [ ] GitHub repository accessible from VPS (public or SSH key added)
- [ ] Domain/subdomain A record pointed at VPS public IP, propagation confirmed (optional for IP-only; required for SSL)
- [ ] OpenAI API key available for manual `.env` entry
- [ ] PRD-01 through PRD-04 complete — application in deployable state

---

## 13. Open Questions

| ID | Question | Priority |
|---|---|---|
| OQ-01 | Domain/subdomain available, or IP-only access? (IP-only = no Certbot SSL) | Must resolve before development begins |
| OQ-02 | Hostinger VPS tier / RAM? Under 1 GB needs swap file configuration in setup.sh | Must resolve before setup.sh is finalized |
| OQ-03 | Parameterize `setup.sh` (domain + repo URL as args), or hardcode for single instance? | Must resolve before development begins |
| OQ-04 | Run service as dedicated `siteaudit` service account, or as SSH deploy user? | Must resolve before service unit finalized |
| OQ-05 | Hostinger provider-level firewall rules requiring alignment with UFW? | Must resolve before firewall hardening step |

---

*End of PRD-05 — VPS Deployment on Hostinger*
*Version 1.0 | 2026-05-05 | Site Audit Agent — Sherwin-Williams PCG Asset Protection*
