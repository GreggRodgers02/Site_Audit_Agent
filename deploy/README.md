# Site Audit Agent — VPS Deployment Guide

APM Site Assessment | Hostinger Ubuntu 22.04 LTS

This guide walks an IT administrator through a complete first-time deployment of the Site Audit Agent. Every command is copy-pasteable. No Python knowledge is required.

---

## 1. Prerequisites

Before beginning, confirm all items below:

- [ ] Hostinger VPS provisioned with **Ubuntu 22.04 LTS** (minimum 1 GB RAM, 20 GB disk)
- [ ] SSH access to the VPS with a user that has `sudo` privileges
- [ ] GitHub repository is accessible from the VPS (public repo, or SSH key added to GitHub)
- [ ] Domain or subdomain **A record** pointed at the VPS public IP (optional for IP-only access; required for HTTPS/SSL)
- [ ] DNS propagation confirmed — run `nslookup yourdomain.com` from any machine and verify it resolves to your VPS IP before running Certbot
- [ ] OpenAI API key obtained from [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- [ ] `deploy/site-audit-agent.service` has been edited to set `User=` to your deploy username (see Step 3 below)
- [ ] `REPO_URL` in `deploy/setup.sh` has been set to your GitHub repository URL

**Hostinger note:** Check your Hostinger control panel for provider-level firewall rules. If Hostinger has a firewall separate from UFW, ensure ports 22, 80, and 443 are allowed there as well.

---

## 2. Quick Start

If your VPS is fresh, your repo URL is set in `setup.sh`, and your domain DNS is already pointing at the server, you can run the full setup in one step:

```bash
# SSH into your VPS, then:
git clone https://github.com/YOUR_ORG/YOUR_REPO.git /srv/site-audit-agent
sudo bash /srv/site-audit-agent/deploy/setup.sh --domain yourdomain.com
```

Then create your `.env` file (see Section 4), start the service, and you're done.

For a step-by-step walkthrough with explanations, follow Section 3.

---

## 3. Step-by-Step Instructions

### Step 1: SSH into the VPS

```bash
ssh your-user@your-server-ip
```

### Step 2: Edit setup.sh before running it

Before running `setup.sh`, you must set the `REPO_URL` variable inside the script. Open it with a text editor:

```bash
sudo nano /path/to/setup.sh
```

Find this line near the top and replace the placeholder:

```bash
REPO_URL="https://github.com/REPLACE_WITH_YOUR_ORG/REPLACE_WITH_YOUR_REPO.git"
```

Save and close (`Ctrl+O`, `Enter`, `Ctrl+X` in nano).

### Step 3: Edit the service file

Open `deploy/site-audit-agent.service` and set `User=` to your deploy username (the SSH user you log in with — do **not** use root):

```bash
nano /path/to/deploy/site-audit-agent.service
```

Find and replace:

```
User=REPLACE_WITH_DEPLOY_USERNAME
```

With your actual username, for example:

```
User=deploy
```

### Step 4: Run the setup script

Run without `--domain` if DNS is not yet propagated, or with `--domain` to have Certbot run automatically:

```bash
# Without domain (HTTP only — run Certbot manually later):
sudo bash /srv/site-audit-agent/deploy/setup.sh

# With domain (Certbot runs automatically):
sudo bash /srv/site-audit-agent/deploy/setup.sh --domain auditapp.example.com
```

The script will install all dependencies, clone the repo, create the Python virtual environment, configure systemd, set up Nginx, and configure UFW. Watch the output for any errors.

### Step 5: Create the .env file

After the script completes, create the environment file with your OpenAI API key:

```bash
sudo nano /srv/site-audit-agent/.env
```

Paste the following (replace the placeholder values — see Section 4 for exact format):

```
OPENAI_API_KEY=sk-your-key-here
OPENAI_PRIMARY_MODEL=gpt-5.5
OPENAI_FALLBACK_MODEL=gpt-5.4
```

Save and close, then lock down permissions:

```bash
sudo chmod 600 /srv/site-audit-agent/.env
```

### Step 6: Start the service

```bash
sudo systemctl start site-audit-agent
sudo systemctl status site-audit-agent
```

The output should show `active (running)`. If it shows `failed`, see Section 7 (Troubleshooting).

### Step 7: Run Certbot for HTTPS (if not done in Step 4)

Your domain's A record must be pointing at the VPS IP before this step. Verify:

```bash
nslookup yourdomain.com
```

Then obtain the certificate:

```bash
sudo certbot --nginx -d yourdomain.com
```

Certbot will inject certificate directives into `/etc/nginx/sites-available/site-audit-agent` and reload Nginx automatically. After this, all HTTP traffic automatically redirects to HTTPS.

To also cover the `www.` subdomain in the same certificate:

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### Step 8: Verify the deployment

Open a browser and navigate to:

- `https://yourdomain.com` (after Certbot), or
- `http://your-server-ip` (before Certbot / IP-only)

The Streamlit UI should load within a few seconds. If you see a 502 Bad Gateway, see Section 7.

---

## 4. Deploying Without a Domain (IP-Only Access)

You do not need a domain name to run the Site Audit Agent. If you do not have one yet, you can deploy over HTTP using your VPS IP address and add a domain later when you're ready.

### How to deploy without a domain

Run the setup script **without** the `--domain` flag:

```bash
sudo bash /srv/site-audit-agent/deploy/setup.sh
```

This installs everything and starts the service, but skips the Certbot SSL step. Your APMs access the tool directly via the VPS IP address:

```
http://YOUR_VPS_IP
```

### How to find your VPS IP address

Log into your Hostinger control panel → **VPS** → select your server. The **IPv4 address** is listed on the overview page. It will look something like `185.241.52.101`.

### What works without a domain

Everything works — AI report generation, PDF export, document library, photo uploads. The only difference is the connection is HTTP (not HTTPS) and APMs use an IP address instead of a name.

### Adding a domain later

When you're ready to add a domain:

1. Log into your domain registrar and add an **A record** pointing your domain (e.g. `audits.yourcompany.com`) to your VPS IP address
2. Wait for DNS to propagate (usually 5–30 minutes) — verify with:
   ```bash
   nslookup audits.yourcompany.com
   ```
3. SSH into the VPS and run Certbot:
   ```bash
   sudo certbot --nginx -d audits.yourcompany.com
   ```

Certbot handles everything — it obtains the SSL certificate, updates the Nginx config, and sets up auto-renewal. No other changes needed. APMs can then access the tool at `https://audits.yourcompany.com`.

---

## 5. .env File Format

The `.env` file at `/srv/site-audit-agent/.env` supplies secrets to the application at runtime. It is **never** committed to git.

**Format — KEY=VALUE, no quotes, no `export` prefix:**

```
OPENAI_API_KEY=sk-your-key-here
OPENAI_PRIMARY_MODEL=gpt-5.5
OPENAI_FALLBACK_MODEL=gpt-5.4
```

**Required variables:**

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key from platform.openai.com |
| `OPENAI_PRIMARY_MODEL` | Primary model name (e.g. `gpt-5.5`) |
| `OPENAI_FALLBACK_MODEL` | Fallback model name used if primary is unavailable |

**After creating or modifying .env, always reset permissions:**

```bash
sudo chmod 600 /srv/site-audit-agent/.env
```

**Then restart the service to apply the new values:**

```bash
sudo systemctl restart site-audit-agent
```

---

## 6. Service Management Commands

### Check service status

```bash
sudo systemctl status site-audit-agent
```

### View live logs (follow mode)

```bash
sudo journalctl -u site-audit-agent -f
```

### View last 50 log lines

```bash
sudo journalctl -u site-audit-agent -n 50
```

### Restart the service

```bash
sudo systemctl restart site-audit-agent
```

### Stop the service

```bash
sudo systemctl stop site-audit-agent
```

### Start the service

```bash
sudo systemctl start site-audit-agent
```

### Enable service to start on boot (already done by setup.sh)

```bash
sudo systemctl enable site-audit-agent
```

---

## 7. Updating the Application

When a new version of the code is pushed to GitHub, deploy it to the VPS with these steps in order:

```bash
# 1. Pull the latest code
cd /srv/site-audit-agent
git pull

# 2. Install any new or updated Python dependencies
/srv/site-audit-agent/venv/bin/pip install -r requirements.txt

# 3. Restart the service
sudo systemctl restart site-audit-agent

# 4. Confirm the service is running
sudo systemctl status site-audit-agent
```

**Note:** If `deploy/nginx.conf` or `deploy/site-audit-agent.service` were updated in the pull, you must also recopy those files:

```bash
# Re-install service unit after changes to the service file
sudo cp /srv/site-audit-agent/deploy/site-audit-agent.service /etc/systemd/system/site-audit-agent.service
sudo systemctl daemon-reload
sudo systemctl restart site-audit-agent

# Re-install Nginx config after changes to nginx.conf
sudo cp /srv/site-audit-agent/deploy/nginx.conf /etc/nginx/sites-available/site-audit-agent
sudo nginx -t
sudo systemctl reload nginx
```

---

## 8. Troubleshooting

### Streamlit port not listening

**Symptom:** Nginx returns 502 immediately; `curl http://127.0.0.1:8501` fails.

**Diagnosis:**

```bash
sudo systemctl status site-audit-agent
sudo journalctl -u site-audit-agent -n 50
```

**Most likely causes:**

- `.env` file does not exist at `/srv/site-audit-agent/.env` — the service fails to load `EnvironmentFile`. Create the `.env` and restart.
- `User=` in the service file is still set to `REPLACE_WITH_DEPLOY_USERNAME`. Edit `/etc/systemd/system/site-audit-agent.service`, set the correct user, then run `sudo systemctl daemon-reload && sudo systemctl restart site-audit-agent`.
- The virtual environment is missing or corrupt — re-run Step 7 of `setup.sh` manually:
  ```bash
  /srv/site-audit-agent/venv/bin/pip install -r /srv/site-audit-agent/requirements.txt
  sudo systemctl restart site-audit-agent
  ```

---

### 502 Bad Gateway

**Symptom:** Browser shows "502 Bad Gateway" when accessing the site.

**Diagnosis:**

```bash
# Check if Streamlit is actually listening
sudo ss -tlnp | grep 8501

# Check the service status and recent logs
sudo journalctl -u site-audit-agent -n 50

# Check Nginx error log
sudo tail -n 30 /var/log/nginx/error.log
```

**Most likely causes:**

- Service is not running — fix the underlying service issue first (see "Streamlit port not listening" above).
- Nginx is proxying to the wrong port — verify `proxy_pass http://127.0.0.1:8501;` in `/etc/nginx/sites-available/site-audit-agent`.
- Nginx config was not reloaded after a change — run `sudo systemctl reload nginx`.

---

### WeasyPrint import errors

**Symptom:** Report generation fails; logs show `ImportError` or `OSError` related to `weasyprint`, `pango`, `cairo`, or `gdk-pixbuf`.

**Diagnosis:**

```bash
sudo journalctl -u site-audit-agent -n 100 | grep -i weasyprint
/srv/site-audit-agent/venv/bin/python -c "import weasyprint; print('OK')"
```

**Most likely cause:** System-level WeasyPrint dependencies were not fully installed before `pip install`. Re-install them:

```bash
sudo apt-get install -y \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libgdk-pixbuf2.0-0 libffi-dev libxml2-dev \
    libxslt1-dev shared-mime-info fonts-liberation

# Then reinstall WeasyPrint itself into the venv
/srv/site-audit-agent/venv/bin/pip install --force-reinstall weasyprint
sudo systemctl restart site-audit-agent
```

---

### SSL certificate errors

**Symptom:** Browser shows "Your connection is not private" or certificate warnings; `curl https://yourdomain.com` fails with SSL errors.

**Diagnosis:**

```bash
# Check certificate status
sudo certbot certificates

# Test renewal (dry run — does not change anything)
sudo certbot renew --dry-run

# Check the Certbot auto-renewal timer
sudo systemctl status certbot.timer
```

**Most likely causes:**

- Certbot has not been run yet — HTTPS is configured in Nginx but no certificate exists. Run: `sudo certbot --nginx -d yourdomain.com`
- Certificate has expired and auto-renewal failed — check `sudo systemctl status certbot.timer` and `sudo journalctl -u certbot`.
- DNS A record does not point at this server — Certbot's ACME challenge will fail. Verify: `nslookup yourdomain.com`

---

### WebSocket connection failures

**Symptom:** Streamlit UI loads but is unresponsive; browser console shows WebSocket errors; report generation hangs or disconnects mid-way.

**Diagnosis:**

```bash
# Verify the Nginx config has all required WebSocket headers
grep -A 20 "location /" /etc/nginx/sites-available/site-audit-agent

# Test Nginx config
sudo nginx -t

# Check Nginx error log for upgrade-related errors
sudo tail -n 30 /var/log/nginx/error.log
```

**Most likely cause:** The Nginx config is missing WebSocket upgrade headers. Confirm `/etc/nginx/sites-available/site-audit-agent` contains:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

If these lines are missing, recopy `deploy/nginx.conf` and reload:

```bash
sudo cp /srv/site-audit-agent/deploy/nginx.conf /etc/nginx/sites-available/site-audit-agent
sudo nginx -t
sudo systemctl reload nginx
```

Also confirm `proxy_buffering off;` is present — buffering breaks WebSocket frame delivery.

---

## 9. Security Notes

- **`.env` permissions:** The `.env` file contains your OpenAI API key and must be locked down. Always verify: `ls -la /srv/site-audit-agent/.env` should show `-rw-------`. If not: `sudo chmod 600 /srv/site-audit-agent/.env`

- **Port 8501 is internal only:** UFW blocks port 8501 from external access. Streamlit binds only to `127.0.0.1`. All external traffic must go through Nginx on ports 80/443. Verify: `sudo ufw status` should list only 22, 80, and 443 as ALLOW.

- **Do not run the service as root:** The `User=` directive in the systemd service file must be set to a non-root user. Running Streamlit as root is a security risk.

- **Disable password-based SSH authentication:** Once SSH key access is confirmed, disable password login on the VPS to prevent brute-force attacks. Edit `/etc/ssh/sshd_config`:
  ```
  PasswordAuthentication no
  ```
  Then restart SSH: `sudo systemctl restart sshd`
  **Only do this after confirming your SSH key login works — otherwise you may lock yourself out.**

- **No secrets in source control:** The `.env` file is excluded from git via `.gitignore`. Never add API keys or passwords to any committed file. The `.env.example` file in the repo contains only placeholder values — it is safe to commit.

- **SSL certificate auto-renewal:** Let's Encrypt certificates expire every 90 days. Certbot installs a systemd timer (`certbot.timer`) that runs renewal checks twice daily. Verify it is active: `sudo systemctl status certbot.timer`

---

*Site Audit Agent — APM Site Assessment*
*Deploy guide version 1.0 | 2026-05-05*
