#!/bin/bash
# Development Environment Setup Script
# Run this script to set up a complete development environment

set -e  # Exit on any error

echo "🚀 Setting up Newspaper Emailer Development Environment"

# Check if Python 3.8+ is available
python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")

python3 -c "import sys; exit(0) if sys.version_info >= (3,8) else exit(1)"
if [ $? -ne 0 ]; then
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

# Install requirements
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p downloads logs templates

# Create initial configuration files if they don't exist
if [ ! -f "config.yaml" ]; then
    echo "⚙️  Creating initial config.yaml..."
    echo "# Configuration file" > config.yaml
fi

if [ ! -f ".env" ]; then
    echo "🔐 Creating initial .env file..."
    echo "# Environment variables for secrets" > .env
    echo "# Add your credentials here" >> .env
fi

echo ""
echo "🎉 Development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit config.yaml with your settings"
echo "2. Edit .env with your credentials"
echo "3. Run: python3 main.py"
echo "4. Schedule with cron or Task Scheduler to run daily"
echo ""
echo "To activate the environment in the future:"
echo "source venv/bin/activate"