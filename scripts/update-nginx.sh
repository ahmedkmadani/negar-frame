#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NGINX_CONF_PATH="/etc/nginx/sites-available/negar-frame.conf"
NGINX_CONF_ENABLED="/etc/nginx/sites-enabled/negar-frame.conf"
LOCAL_CONF_PATH="${SCRIPT_DIR}/negar-frame.conf"

# Function to print status messages
print_status() {
    echo -e "${YELLOW}[*] $1${NC}"
}

print_success() {
    echo -e "${GREEN}[✓] $1${NC}"
}

print_error() {
    echo -e "${RED}[✗] $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Check if local configuration file exists
if [ ! -f "$LOCAL_CONF_PATH" ]; then
    print_error "Local configuration file not found at $LOCAL_CONF_PATH"
    exit 1
fi

# Backup current configuration
print_status "Creating backup of current Nginx configuration..."
BACKUP_PATH="/etc/nginx/sites-available/frame.leamech.com.backup.$(date +%Y%m%d_%H%M%S)"
if cp "$NGINX_CONF_PATH" "$BACKUP_PATH"; then
    print_success "Backup created at $BACKUP_PATH"
else
    print_error "Failed to create backup"
    exit 1
fi

# Copy new configuration
print_status "Copying new configuration..."
cp "$LOCAL_CONF_PATH" "$NGINX_CONF_PATH"

# Test Nginx configuration
print_status "Testing Nginx configuration..."
nginx -t

if [ $? -ne 0 ]; then
    print_error "Nginx configuration test failed"
    print_status "Restoring backup..."
    cp "$BACKUP_PATH" "$NGINX_CONF_PATH"
    print_status "Please check your configuration and try again"
    exit 1
fi

# Reload Nginx
print_status "Reloading Nginx..."
systemctl reload nginx

if [ $? -eq 0 ]; then
    print_success "Nginx reloaded successfully"
else
    print_error "Failed to reload Nginx"
    print_status "Restoring backup..."
    cp "$BACKUP_PATH" "$NGINX_CONF_PATH"
    systemctl reload nginx
    exit 1
fi

# Check if Nginx is running
if systemctl is-active --quiet nginx; then
    print_success "Nginx is running"
else
    print_error "Nginx is not running"
    print_status "Attempting to start Nginx..."
    systemctl start nginx
fi

# Final status check
print_status "Checking Nginx status..."
systemctl status nginx --no-pager

print_success "Update complete!"
echo -e "${GREEN}Backup file: $BACKUP_PATH${NC}" 