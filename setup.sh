#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root (not recommended)
if [ "$EUID" -eq 0 ]; then 
   print_warning "Please don't run this script as root!"
   exit 1
fi

# Detect OS
OS=""
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
else
    print_error "Unsupported operating system: $OSTYPE"
    exit 1
fi

print_info "Detected OS: $OS"

# Function to install Docker on Ubuntu/Debian
install_docker_debian() {
    print_info "Installing Docker on Debian/Ubuntu..."
    
    # Update package index
    sudo apt-get update
    
    # Install prerequisites
    sudo apt-get install -y \
        ca-certificates \
        curl \
        gnupg \
        lsb-release
    
    # Add Docker's official GPG key
    sudo mkdir -m 0755 -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$OS/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    # Set up the repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$OS \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker Engine
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Add current user to docker group
    sudo usermod -aG docker $USER
    
    print_info "Docker installed successfully!"
    print_warning "You need to log out and back in for group changes to take effect."
}

# Function to install Docker on macOS
install_docker_macos() {
    print_info "Installing Docker on macOS..."
    
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        print_error "Homebrew is not installed. Please install Homebrew first:"
        print_error "Visit: https://brew.sh"
        exit 1
    fi
    
    # Install Docker Desktop
    brew install --cask docker
    
    print_info "Docker Desktop installed successfully!"
    print_warning "Please start Docker Desktop from Applications folder."
}

# Function to install Docker on Fedora
install_docker_fedora() {
    print_info "Installing Docker on Fedora..."
    
    # Remove old versions
    sudo dnf remove -y docker \
                     docker-client \
                     docker-client-latest \
                     docker-common \
                     docker-latest \
                     docker-latest-logrotate \
                     docker-logrotate \
                     docker-selinux \
                     docker-engine-selinux \
                     docker-engine
    
    # Set up the repository
    sudo dnf -y install dnf-plugins-core
    sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
    
    # Install Docker Engine
    sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Start Docker
    sudo systemctl start docker
    sudo systemctl enable docker
    
    # Add current user to docker group
    sudo usermod -aG docker $USER
    
    print_info "Docker installed successfully!"
    print_warning "You need to log out and back in for group changes to take effect."
}

# Check if Docker is already installed
if command -v docker &> /dev/null; then
    docker_version=$(docker --version)
    print_info "Docker is already installed: $docker_version"
    
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        print_warning "Docker daemon is not running. Please start Docker."
        if [[ "$OS" == "macos" ]]; then
            print_info "Start Docker Desktop from Applications folder."
        else
            print_info "Try: sudo systemctl start docker"
        fi
    fi
else
    # Install Docker based on OS
    case $OS in
        ubuntu|debian)
            install_docker_debian
            ;;
        fedora)
            install_docker_fedora
            ;;
        macos)
            install_docker_macos
            ;;
        *)
            print_error "Unsupported OS for automatic Docker installation: $OS"
            print_info "Please install Docker manually from: https://docs.docker.com/get-docker/"
            exit 1
            ;;
    esac
fi

# Check Python version
print_info "Checking Python version..."
if command -v python3 &> /dev/null; then
    python_version=$(python3 --version)
    print_info "Python installed: $python_version"
    
    # Check if Python 3.11+ is installed
    python_major=$(python3 -c 'import sys; print(sys.version_info.major)')
    python_minor=$(python3 -c 'import sys; print(sys.version_info.minor)')
    
    if [ "$python_major" -eq 3 ] && [ "$python_minor" -ge 11 ]; then
        print_info "Python version meets requirements (3.11+)"
    else
        print_warning "Python 3.11+ is required. Current version: $python_version"
        print_info "Please upgrade Python to 3.11 or higher."
    fi
else
    print_error "Python 3 is not installed. Please install Python 3.11+."
    exit 1
fi

# Set up Python virtual environment
print_info "Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_info "Virtual environment created."
else
    print_info "Virtual environment already exists."
fi

# Activate virtual environment
source venv/bin/activate

# Install project dependencies
print_info "Installing project dependencies..."
pip install -e .

# Create necessary directories
print_info "Creating necessary directories..."
mkdir -p data

# Copy environment file if it doesn't exist
if [ ! -f ".env" ]; then
    if [ -f "env.example" ]; then
        cp env.example .env
        print_info "Created .env file from env.example"
        print_warning "Please edit .env file and add your API keys and configuration."
    else
        print_error "env.example file not found!"
    fi
else
    print_info ".env file already exists."
fi

# Final instructions
echo
print_info "Setup complete!"
echo
echo "Next steps:"
echo "1. Ensure Docker is running:"
if [[ "$OS" == "macos" ]]; then
    echo "   - Start Docker Desktop from Applications"
else
    echo "   - sudo systemctl start docker (if not already running)"
fi
echo "2. Edit .env file with your configuration:"
echo "   - Add your ANTHROPIC_API_KEY for Claude repository analysis"
echo "   - Configure other settings as needed"
echo "3. Activate the virtual environment:"
echo "   - source venv/bin/activate"
echo "4. Start the web interface:"
echo "   - python -m mcp_router.web"
echo "5. Open http://localhost:8000 in your browser"
echo
print_warning "If you just installed Docker, you may need to log out and back in for group permissions to take effect." 