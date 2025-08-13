#!/bin/bash
# Environment Setup Script for MQI Communicator System

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV="${1:-production}"
INSTALL_RABBITMQ="${INSTALL_RABBITMQ:-true}"
INSTALL_DEPS="${INSTALL_DEPS:-true}"
VERBOSE="${VERBOSE:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Detect OS and distribution
# Deploy configuration files
deploy_config() {
    log_info "Deploying configuration files for $ENV environment..."
    
    # Create config directory if it doesn't exist
    mkdir -p "$PROJECT_ROOT/config"
    
    # Copy default configuration if environment config doesn't exist
    if [[ ! -f "$PROJECT_ROOT/config/config.$ENV.yaml" ]]; then
        cp "$PROJECT_ROOT/config/config.default.yaml" "$PROJECT_ROOT/config/config.$ENV.yaml"
        log_success "Created new configuration for $ENV environment"
    fi
    
    # Encrypt sensitive credentials if needed
    if [[ "$1" == "--encrypt-creds" ]]; then
        python "$PROJECT_ROOT/scripts/encrypt_credentials.py" "$ENV"
    fi
}

# Deploy system components
deploy_system() {
    log_info "Deploying system components for $ENV environment..."
    
    # Ensure configuration exists
    if [[ ! -f "$PROJECT_ROOT/config/config.$ENV.yaml" ]]; then
        log_error "Configuration file not found for $ENV environment"
        exit 1
    fi
    
    # Create required directories
    mkdir -p "$PROJECT_ROOT/logs"
    mkdir -p "$PROJECT_ROOT/data"
    
    # Set correct permissions
    chmod -R 755 "$PROJECT_ROOT/scripts"
    chmod -R 644 "$PROJECT_ROOT/config/config.$ENV.yaml"
}

detect_os() {
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        OS=$ID
        VERSION=$VERSION_ID
    else
        log_error "Cannot detect operating system"
        exit 1
    fi
    
    log_info "Detected OS: $OS $VERSION"
}

# Install system dependencies
install_system_dependencies() {
    if [[ "$INSTALL_DEPS" != "true" ]]; then
        log_info "Skipping system dependencies installation"
        return
    fi
    
    log_info "Installing system dependencies..."
    
    case $OS in
        ubuntu|debian)
            sudo apt-get update
            
            # Basic dependencies
            sudo apt-get install -y \
                python3 \
                python3-pip \
                python3-venv \
                python3-dev \
                sqlite3 \
                git \
                curl \
                wget \
                build-essential \
                pkg-config \
                libffi-dev \
                libssl-dev
            
            # For SSH and SFTP functionality
            sudo apt-get install -y \
                openssh-client \
                libssh2-1-dev
            
            log_success "System dependencies installed (Ubuntu/Debian)"
            ;;
            
        centos|rhel|fedora)
            if command -v dnf &> /dev/null; then
                PKG_MGR="dnf"
            else
                PKG_MGR="yum"
            fi
            
            sudo $PKG_MGR update -y
            
            # Basic dependencies
            sudo $PKG_MGR install -y \
                python3 \
                python3-pip \
                python3-devel \
                sqlite \
                git \
                curl \
                wget \
                gcc \
                gcc-c++ \
                make \
                pkgconfig \
                libffi-devel \
                openssl-devel
            
            # For SSH and SFTP functionality
            sudo $PKG_MGR install -y \
                openssh-clients \
                libssh2-devel
            
            log_success "System dependencies installed (RHEL/CentOS/Fedora)"
            ;;
            
        *)
            log_warning "Unsupported OS: $OS. Please install dependencies manually:"
            echo "  - python3, python3-pip, python3-venv"
            echo "  - sqlite3, git, curl, wget"
            echo "  - build-essential, libssl-dev, libffi-dev"
            echo "  - openssh-client"
            ;;
    esac
}

# Install RabbitMQ
install_rabbitmq() {
    if [[ "$INSTALL_RABBITMQ" != "true" ]]; then
        log_info "Skipping RabbitMQ installation"
        return
    fi
    
    log_info "Installing RabbitMQ..."
    
    case $OS in
        ubuntu|debian)
            # Add RabbitMQ repository
            curl -fsSL https://github.com/rabbitmq/signing-keys/releases/download/2.0/rabbitmq-release-signing-key.asc | sudo apt-key add -
            echo "deb https://dl.bintray.com/rabbitmq/debian $(lsb_release -sc) main" | sudo tee /etc/apt/sources.list.d/bintray.rabbitmq.list
            
            sudo apt-get update
            sudo apt-get install -y rabbitmq-server
            
            # Enable and start RabbitMQ
            sudo systemctl enable rabbitmq-server
            sudo systemctl start rabbitmq-server
            
            log_success "RabbitMQ installed and started (Ubuntu/Debian)"
            ;;
            
        centos|rhel|fedora)
            # Install Erlang first
            sudo $PKG_MGR install -y epel-release
            sudo $PKG_MGR install -y erlang
            
            # Install RabbitMQ
            sudo $PKG_MGR install -y rabbitmq-server
            
            # Enable and start RabbitMQ
            sudo systemctl enable rabbitmq-server
            sudo systemctl start rabbitmq-server
            
            log_success "RabbitMQ installed and started (RHEL/CentOS/Fedora)"
            ;;
            
        *)
            log_warning "Please install RabbitMQ manually for OS: $OS"
            echo "Visit: https://www.rabbitmq.com/install-debian.html"
            ;;
    esac
    
    # Configure RabbitMQ
    if systemctl is-active --quiet rabbitmq-server; then
        log_info "Configuring RabbitMQ..."
        
        # Enable management plugin
        sudo rabbitmq-plugins enable rabbitmq_management
        
        # Create admin user (optional, for web management)
        if [[ "${CREATE_ADMIN_USER:-false}" == "true" ]]; then
            sudo rabbitmqctl add_user admin "${RABBITMQ_ADMIN_PASSWORD:-admin123}"
            sudo rabbitmqctl set_user_tags admin administrator
            sudo rabbitmqctl set_permissions -p / admin ".*" ".*" ".*"
            log_info "RabbitMQ admin user created (username: admin)"
        fi
        
        log_success "RabbitMQ configuration complete"
    fi
}

# Setup firewall rules
setup_firewall() {
    log_info "Configuring firewall rules..."
    
    if command -v ufw &> /dev/null; then
        # Ubuntu/Debian UFW
        log_info "Detected UFW firewall"
        
        # Allow SSH
        sudo ufw allow ssh
        
        # Allow RabbitMQ (if needed from external)
        if [[ "${ALLOW_EXTERNAL_RABBITMQ:-false}" == "true" ]]; then
            sudo ufw allow 5672/tcp  # AMQP port
            sudo ufw allow 15672/tcp # Management web interface
            log_info "Opened RabbitMQ ports for external access"
        fi
        
        # Enable firewall if not already enabled
        sudo ufw --force enable
        
        log_success "UFW firewall configured"
        
    elif command -v firewall-cmd &> /dev/null; then
        # RHEL/CentOS/Fedora firewalld
        log_info "Detected firewalld"
        
        # Allow SSH
        sudo firewall-cmd --permanent --add-service=ssh
        
        # Allow RabbitMQ (if needed from external)
        if [[ "${ALLOW_EXTERNAL_RABBITMQ:-false}" == "true" ]]; then
            sudo firewall-cmd --permanent --add-port=5672/tcp
            sudo firewall-cmd --permanent --add-port=15672/tcp
            log_info "Opened RabbitMQ ports for external access"
        fi
        
        # Reload firewall
        sudo firewall-cmd --reload
        
        log_success "Firewalld configured"
        
    else
        log_warning "No supported firewall found. Please configure manually if needed."
    fi
}

# Create system user for service (production)
create_service_user() {
    local username="${SERVICE_USER:-mqi-comm}"
    
    if [[ "${CREATE_SERVICE_USER:-false}" != "true" ]]; then
        log_info "Skipping service user creation"
        return
    fi
    
    log_info "Creating service user: $username"
    
    if ! id "$username" &>/dev/null; then
        sudo useradd --system --create-home --shell /bin/bash "$username"
        log_success "Service user created: $username"
    else
        log_info "Service user already exists: $username"
    fi
    
    # Set up directory permissions
    sudo chown -R "$username:$username" "$PROJECT_ROOT/data"
    sudo chown -R "$username:$username" "$PROJECT_ROOT/logs"
    sudo chown -R "$username:$username" "$PROJECT_ROOT/backups"
    
    log_success "Directory permissions set for service user"
}

# Setup log rotation
setup_log_rotation() {
    log_info "Setting up log rotation..."
    
    local logrotate_config="/etc/logrotate.d/mqi-communicator"
    
    sudo tee "$logrotate_config" > /dev/null <<EOF
$PROJECT_ROOT/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 ${SERVICE_USER:-$USER} ${SERVICE_USER:-$USER}
    postrotate
        # Send HUP signal to main process to reopen log files
        pkill -HUP -f "main_orchestrator.py" || true
    endscript
}
EOF
    
    log_success "Log rotation configured"
}

# Install Python dependencies
install_python_dependencies() {
    log_info "Installing Python dependencies..."
    
    cd "$PROJECT_ROOT"
    
    # Create virtual environment if it doesn't exist
    if [[ ! -d "venv" ]]; then
        python3 -m venv venv
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    python3 -m pip install --upgrade pip
    
    # Install dependencies
    if [[ -f "requirements.txt" ]]; then
        pip3 install -r requirements.txt
    else
        log_warning "requirements.txt not found, installing basic dependencies..."
        pip3 install pika pyyaml paramiko apscheduler psutil
    fi
    
    log_success "Python dependencies installed"
}

# Performance tuning
tune_system_performance() {
    log_info "Applying system performance tuning..."
    
    # Increase file descriptor limits
    echo "* soft nofile 65536" | sudo tee -a /etc/security/limits.conf
    echo "* hard nofile 65536" | sudo tee -a /etc/security/limits.conf
    
    # Tune network settings for better throughput
    sudo tee -a /etc/sysctl.conf <<EOF

# MQI Communicator system tuning
net.core.somaxconn = 1024
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_max_syn_backlog = 1024
net.ipv4.tcp_congestion_control = bbr
EOF
    
    # Apply sysctl changes
    sudo sysctl -p
    
    log_success "System performance tuning applied"
}

# Create systemd tmpfiles configuration
setup_tmpfiles() {
    log_info "Setting up systemd tmpfiles configuration..."
    
    sudo tee /etc/tmpfiles.d/mqi-communicator.conf <<EOF
# MQI Communicator temporary file cleanup
d $PROJECT_ROOT/tmp 0755 ${SERVICE_USER:-$USER} ${SERVICE_USER:-$USER} 1d
EOF
    
    # Create the temporary directory
    sudo systemd-tmpfiles --create /etc/tmpfiles.d/mqi-communicator.conf
    
    log_success "Tmpfiles configuration created"
}

# Validate environment setup
validate_environment() {
    log_info "Validating environment setup..."
    
    local errors=()
    
    # Check Python
    if ! python3 --version &>/dev/null; then
        errors+=("Python 3 not available")
    fi
    
    # Check pip
    if ! pip3 --version &>/dev/null; then
        errors+=("pip3 not available")
    fi
    
    # Check SQLite
    if ! sqlite3 --version &>/dev/null; then
        errors+=("SQLite3 not available")
    fi
    
    # Check RabbitMQ (if installed)
    if [[ "$INSTALL_RABBITMQ" == "true" ]]; then
        if ! systemctl is-active --quiet rabbitmq-server; then
            errors+=("RabbitMQ service not running")
        fi
    fi
    
    # Check project structure
    for dir in data logs; do
        if [[ ! -d "$PROJECT_ROOT/$dir" ]]; then
            errors+=("Directory missing: $dir")
        fi
    done
    
    if [[ ${#errors[@]} -eq 0 ]]; then
        log_success "Environment validation passed"
        return 0
    else
        log_error "Environment validation failed:"
        for error in "${errors[@]}"; do
            echo "  - $error"
        done
        return 1
    fi
}

# Show completion summary
show_summary() {
    log_success "Environment setup completed!"
    echo ""
    echo "Summary of what was installed/configured:"
    echo "  ✓ System dependencies (Python, SQLite, build tools)"
    
    if [[ "$INSTALL_RABBITMQ" == "true" ]]; then
        echo "  ✓ RabbitMQ message broker"
    fi
    
    echo "  ✓ Python virtual environment"
    echo "  ✓ Firewall rules"
    echo "  ✓ Log rotation"
    echo "  ✓ System performance tuning"
    
    if [[ "${CREATE_SERVICE_USER:-false}" == "true" ]]; then
        echo "  ✓ Service user: ${SERVICE_USER:-mqi-comm}"
    fi
    
    echo ""
    echo "Next steps:"
    echo "  1. Run deployment script: ./scripts/deploy_system.sh production"
    echo "  2. Customize configuration: config/config.production.yaml"
    echo "  3. Start the system"
    
    if [[ "$INSTALL_RABBITMQ" == "true" ]]; then
        echo ""
        echo "RabbitMQ Management Interface:"
        echo "  URL: http://localhost:15672"
        if [[ "${CREATE_ADMIN_USER:-false}" == "true" ]]; then
            echo "  Username: admin"
            echo "  Password: ${RABBITMQ_ADMIN_PASSWORD:-admin123}"
        fi
    fi
}

# Main function
main() {
    log_info "Starting MQI Communicator environment setup..."
    
    detect_os
    install_system_dependencies
    install_rabbitmq
    install_python_dependencies
    setup_firewall
    create_service_user
    setup_log_rotation
    setup_tmpfiles
    tune_system_performance
    
    if validate_environment; then
        show_summary
    else
        log_error "Environment setup completed with errors. Please review and fix issues."
        exit 1
    fi
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Environment Variables:"
        echo "  INSTALL_RABBITMQ=false    Skip RabbitMQ installation"
        echo "  INSTALL_DEPS=false        Skip system dependency installation"
        echo "  CREATE_SERVICE_USER=true  Create dedicated service user"
        echo "  SERVICE_USER=mqi-comm     Service user name"
        echo "  CREATE_ADMIN_USER=true    Create RabbitMQ admin user"
        echo "  RABBITMQ_ADMIN_PASSWORD   Password for RabbitMQ admin user"
        echo "  ALLOW_EXTERNAL_RABBITMQ   Allow external access to RabbitMQ"
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac