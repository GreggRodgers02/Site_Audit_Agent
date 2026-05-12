#!/bin/bash
# =============================================================================
# setup.sh — Site Audit Agent VPS Provisioning Script
# APM Site Assessment
# Target OS: Ubuntu 22.04 LTS
# =============================================================================
#
# BEFORE RUNNING:
#   1. Set REPO_URL below to your GitHub repository URL, e.g.:
#          REPO_URL="https://github.com/your-org/site-audit-agent.git"
#   2. Open deploy/site-audit-agent.service and set User= to your deploy user.
#   3. Run this script as root or with sudo:
#          sudo bash deploy/setup.sh
#      Or with an optional domain for automatic Certbot SSL:
#          sudo bash deploy/setup.sh --domain auditapp.example.com
#
# This script is idempotent — safe to re-run after failures.
# =============================================================================

set -e

# =============================================================================
# CONFIGURATION — Fill in before running
# =============================================================================

# Your GitHub repository URL. Replace this with the actual URL.
REPO_URL="https://github.com/REPLACE_WITH_YOUR_ORG/REPLACE_WITH_YOUR_REPO.git"

# Installation directory (matches systemd service and nginx config)
INSTALL_DIR="/srv/site-audit-agent"

# Service name (must match the .service filename)
SERVICE_NAME="site-audit-agent"

# =============================================================================
# Argument parsing — optional --domain flag
# =============================================================================

DOMAIN=""
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --domain)
            DOMAIN="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: sudo bash setup.sh [--domain yourdomain.com]"
            exit 1
            ;;
    esac
done

# =============================================================================
# Helper functions
# =============================================================================

print_header() {
    echo ""
    echo "============================================================"
    echo "  Site Audit Agent — VPS Setup"
    echo "  APM Site Assessment"
    echo "  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================================"
    echo ""
}

step() {
    echo ""
    echo "------------------------------------------------------------"
    echo "  STEP $1: $2"
    echo "------------------------------------------------------------"
}

ok() {
    echo "  [OK] $1"
}

# =============================================================================
# Pre-flight checks
# =============================================================================

print_header

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: This script must be run as root or with sudo."
    echo "Usage: sudo bash setup.sh [--domain yourdomain.com]"
    exit 1
fi

if [[ "$REPO_URL" == *"REPLACE_WITH"* ]]; then
    echo "ERROR: REPO_URL has not been set. Edit setup.sh and set REPO_URL before running."
    exit 1
fi

echo "  Install directory : $INSTALL_DIR"
echo "  Service name      : $SERVICE_NAME"
echo "  Repository URL    : $REPO_URL"
if [[ -n "$DOMAIN" ]]; then
    echo "  Domain            : $DOMAIN (Certbot will run automatically)"
else
    echo "  Domain            : not provided (Certbot must be run manually)"
fi

# =============================================================================
# Step 1: System update
# =============================================================================

step 1 "Updating system packages"
apt-get update -y
apt-get upgrade -y
ok "System packages updated"

# =============================================================================
# Step 2: Install Python 3.11
# =============================================================================

step 2 "Installing Python 3.11, pip, and venv"
apt-get install -y python3.11 python3.11-venv python3-pip
ok "Python 3.11 installed: $(python3.11 --version)"

# =============================================================================
# Step 3: Install WeasyPrint system dependencies
# These must be installed BEFORE pip install to avoid WeasyPrint import errors.
# =============================================================================

step 3 "Installing WeasyPrint system dependencies"
apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    shared-mime-info \
    fonts-liberation
ok "WeasyPrint system dependencies installed"

# =============================================================================
# Step 4: Install Nginx
# =============================================================================

step 4 "Installing Nginx"
apt-get install -y nginx
ok "Nginx installed: $(nginx -v 2>&1)"

# =============================================================================
# Step 5: Install Certbot
# =============================================================================

step 5 "Installing Certbot and python3-certbot-nginx"
apt-get install -y certbot python3-certbot-nginx
ok "Certbot installed: $(certbot --version)"

# =============================================================================
# Step 6: Clone or update repository
# =============================================================================

step 6 "Cloning/updating repository to $INSTALL_DIR"

if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo "  Repository already exists — pulling latest changes"
    git -C "$INSTALL_DIR" pull
    ok "Repository updated"
else
    echo "  Cloning repository from $REPO_URL"
    git clone "$REPO_URL" "$INSTALL_DIR"
    ok "Repository cloned to $INSTALL_DIR"
fi

# =============================================================================
# Step 7: Create Python virtual environment and install dependencies
# =============================================================================

step 7 "Creating virtual environment and installing Python dependencies"

if [[ ! -d "$INSTALL_DIR/venv" ]]; then
    echo "  Creating virtual environment at $INSTALL_DIR/venv"
    python3.11 -m venv "$INSTALL_DIR/venv"
    ok "Virtual environment created"
else
    echo "  Virtual environment already exists — skipping creation"
fi

echo "  Installing requirements from requirements.txt"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
ok "Python dependencies installed"

# =============================================================================
# Step 8: Install and enable systemd service
# =============================================================================

step 8 "Installing and enabling systemd service"

cp "$INSTALL_DIR/deploy/site-audit-agent.service" "/etc/systemd/system/$SERVICE_NAME.service"
chmod 644 "/etc/systemd/system/$SERVICE_NAME.service"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

# Attempt to start; if .env is missing the service will fail — that's expected
# and the user will be instructed to create it below.
if [[ -f "$INSTALL_DIR/.env" ]]; then
    systemctl start "$SERVICE_NAME" || true
    ok "Service started (check status with: systemctl status $SERVICE_NAME)"
else
    echo "  NOTE: .env not found — service will not start until .env is created."
    echo "  See 'Next Steps' at the end of this script."
fi

ok "Service installed and enabled"

# =============================================================================
# Step 9: Configure Nginx
# =============================================================================

step 9 "Configuring Nginx reverse proxy"

NGINX_AVAILABLE="/etc/nginx/sites-available/$SERVICE_NAME"
NGINX_ENABLED="/etc/nginx/sites-enabled/$SERVICE_NAME"

cp "$INSTALL_DIR/deploy/nginx.conf" "$NGINX_AVAILABLE"
chmod 644 "$NGINX_AVAILABLE"

# Create symlink in sites-enabled (idempotent)
if [[ ! -L "$NGINX_ENABLED" ]]; then
    ln -s "$NGINX_AVAILABLE" "$NGINX_ENABLED"
    ok "Nginx config symlinked to sites-enabled"
else
    echo "  Nginx symlink already exists — skipping"
fi

# Remove the default Nginx site to avoid conflicts
if [[ -L "/etc/nginx/sites-enabled/default" ]]; then
    rm "/etc/nginx/sites-enabled/default"
    ok "Default Nginx site removed"
fi

# Test configuration and reload
nginx -t
systemctl reload nginx
ok "Nginx configured and reloaded"

# =============================================================================
# Step 10: Configure UFW firewall
# =============================================================================

step 10 "Configuring UFW firewall"

ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

ok "UFW enabled — ports 22, 80, 443 open; port 8501 blocked externally"

# =============================================================================
# Step 11: Set .env file permissions
# =============================================================================

step 11 "Checking .env file permissions"

if [[ -f "$INSTALL_DIR/.env" ]]; then
    chmod 600 "$INSTALL_DIR/.env"
    ok ".env permissions set to 600"
else
    echo "  .env not found — skipping (create it before starting the service)"
fi

# =============================================================================
# Step 12: Run Certbot (if --domain was provided)
# =============================================================================

step 12 "SSL certificate (Certbot)"

if [[ -n "$DOMAIN" ]]; then
    echo "  Running Certbot for domain: $DOMAIN"
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@"$DOMAIN"
    systemctl reload nginx
    ok "SSL certificate obtained for $DOMAIN"
else
    echo "  --domain not provided — skipping automatic Certbot run"
    echo "  Run Certbot manually after DNS is confirmed:"
    echo "    sudo certbot --nginx -d yourdomain.com"
fi

# =============================================================================
# Final: Success message and next steps
# =============================================================================

echo ""
echo "============================================================"
echo "  SETUP COMPLETE"
echo "============================================================"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Create the .env file with your OpenAI API key:"
echo ""
echo "     sudo nano $INSTALL_DIR/.env"
echo ""
echo "     Paste the following (replace sk-... with your real key):"
echo ""
echo "       OPENAI_API_KEY=sk-your-key-here"
echo "       OPENAI_PRIMARY_MODEL=gpt-5.5"
echo "       OPENAI_FALLBACK_MODEL=gpt-5.4"
echo ""
echo "     Then set permissions:"
echo "       sudo chmod 600 $INSTALL_DIR/.env"
echo ""
echo "  2. Update the service user in site-audit-agent.service:"
echo "     Open /etc/systemd/system/$SERVICE_NAME.service and set"
echo "     User= to your deploy username, then run:"
echo "       sudo systemctl daemon-reload"
echo ""
echo "  3. Start the service:"
echo "       sudo systemctl start $SERVICE_NAME"
echo "       sudo systemctl status $SERVICE_NAME"
echo ""

if [[ -z "$DOMAIN" ]]; then
    echo "  4. Obtain an SSL certificate (requires DNS A record pointing to this IP):"
    echo "       sudo certbot --nginx -d yourdomain.com"
    echo ""
fi

echo "  5. Check the application is accessible in your browser:"
if [[ -n "$DOMAIN" ]]; then
    echo "       https://$DOMAIN"
else
    echo "       http://<your-server-ip>  (HTTP only until Certbot is run)"
fi

echo ""
echo "  For service management, see deploy/README.md"
echo ""
