#!/bin/bash
# Development Environment Setup Script
# Run this script to set up a complete development environment

set -e  # Exit on any error

echo "🚀 Setting up Newspaper Emailer Development Environment"

# Check if Python 3.8+ is available
python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Error: Python 3.8 or higher is required. Found: $python_version"
    exit 1
fi

echo "✅ Python version: $python_version"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install basic requirements
echo "📚 Installing basic requirements..."
pip install -r requirements_basic.txt

# Install development requirements
echo "🔧 Installing development requirements..."
pip install -r requirements.txt

# Install development tools
echo "🛠️  Installing development tools..."
pip install pytest pytest-cov coverage black flake8

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p downloads logs templates

# Create initial configuration files if they don't exist
if [ ! -f "config.yaml" ]; then
    echo "⚙️  Creating initial config.yaml..."
    cp config.yaml.example config.yaml 2>/dev/null || echo "# Configuration file" > config.yaml
fi

if [ ! -f ".env" ]; then
    echo "🔐 Creating initial .env file..."
    echo "# Environment variables for secrets" > .env
    echo "# Add your credentials here" >> .env
fi

# Set up pre-commit hooks (optional)
if command -v pre-commit &> /dev/null; then
    echo "🔗 Setting up pre-commit hooks..."
    pre-commit install
fi

echo ""
echo "🎉 Development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit config.yaml with your settings"
echo "2. Edit .env with your credentials"
echo "3. Run: python3 run_newspaper.py --onboarding"
echo "4. Test: python3 run_newspaper.py --health"
echo "5. Start GUI: python3 gui_app.py"
echo ""
echo "To activate the environment in the future:"
echo "source venv/bin/activate"