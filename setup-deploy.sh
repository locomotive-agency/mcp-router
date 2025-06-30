#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_info "Setting up MCP Router for deployment environment..."

# Check Docker availability
print_info "Checking Docker availability..."
if command -v docker &> /dev/null; then
    if docker info &> /dev/null 2>&1; then
        print_info "Docker is available and accessible"
    else
        print_info "WARNING: Docker command found but daemon not accessible"
        print_info "This may cause issues with MCP server functionality"
        print_info "Ensure Docker daemon is running and accessible"
    fi
else
    print_info "WARNING: Docker not found in deployment environment"
    print_info "MCP Router requires Docker for container-based MCP servers"
    print_info "Consider using a deployment platform that supports Docker"
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
        print_info "Python version: $python_version (deployment environment handles this)"
    fi
else
    print_info "Python check skipped (deployment environment handles this)"
fi

# Set up Python virtual environment (if not in deployment)
if [ -z "$RENDER" ] && [ -z "$VERCEL" ] && [ -z "$HEROKU" ]; then
    print_info "Setting up Python virtual environment..."
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_info "Virtual environment created."
    else
        print_info "Virtual environment already exists."
    fi
    
    # Activate virtual environment
    source venv/bin/activate
else
    print_info "Skipping virtual environment setup (deployment environment)"
fi

# Install project dependencies
print_info "Installing project dependencies..."
pip install -e .

# Create data directory
print_info "Creating data directory..."
mkdir -p data

# Create .env from template if it doesn't exist
if [ ! -f ".env" ] && [ -f "env.example" ]; then
    print_info "Creating .env from template..."
    cp env.example .env
    print_info "Please edit .env with your configuration values"
fi

print_info "Setup complete!"
print_info "Note: Docker functionality for MCP servers will be limited in deployment environments" 