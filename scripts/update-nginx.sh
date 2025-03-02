#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NGINX_MINIO_CONF_PATH="/etc/nginx/sites-available/dev-minio.leamech.com"
LOCAL_MINIO_CONF_PATH="${SCRIPT_DIR}/dev-minio.leamech.com.conf"

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
if [ ! -f "$LOCAL_MINIO_CONF_PATH" ]; then
    print_error "Local MinIO configuration file not found at $LOCAL_MINIO_CONF_PATH"
    exit 1
fi

# Backup current configuration
print_status "Creating backup of current MinIO Nginx configuration..."
BACKUP_MINIO_PATH="/etc/nginx/sites-available/dev-minio.leamech.com.backup.$(date +%Y%m%d_%H%M%S)"
if [ -f "$NGINX_MINIO_CONF_PATH" ]; then
    cp "$NGINX_MINIO_CONF_PATH" "$BACKUP_MINIO_PATH"
    print_success "Backup created at $BACKUP_MINIO_PATH"
fi

# Copy new configuration
print_status "Copying new MinIO configuration..."
cp "$LOCAL_MINIO_CONF_PATH" "$NGINX_MINIO_CONF_PATH"

# Create symbolic link if it doesn't exist
if [ ! -L "/etc/nginx/sites-enabled/dev-minio.leamech.com" ]; then
    ln -s "$NGINX_MINIO_CONF_PATH" "/etc/nginx/sites-enabled/"
fi

# Test Nginx configuration
print_status "Testing Nginx configuration..."
nginx -t

if [ $? -ne 0 ]; then
    print_error "Nginx configuration test failed"
    print_status "Restoring backup..."
    [ -f "$BACKUP_MINIO_PATH" ] && cp "$BACKUP_MINIO_PATH" "$NGINX_MINIO_CONF_PATH"
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
    [ -f "$BACKUP_MINIO_PATH" ] && cp "$BACKUP_MINIO_PATH" "$NGINX_MINIO_CONF_PATH"
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
[ -f "$BACKUP_MINIO_PATH" ] && echo -e "${GREEN}MinIO backup file: $BACKUP_MINIO_PATH${NC}" 