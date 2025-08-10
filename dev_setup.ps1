# Development Environment Setup Script for Windows
# Run this script in PowerShell as Administrator

param(
    [switch]$SkipVirtualEnv
)

Write-Host "🚀 Setting up Newspaper Emailer Development Environment" -ForegroundColor Green

# Check if Python 3.8+ is available
try {
    $pythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Error: Python not found. Please install Python 3.8 or higher." -ForegroundColor Red
        exit 1
    }

    # Validate pythonVersion format (should be like "3.8" or "3.10")
    if (-not ($pythonVersion -match '^\d+\.\d+$')) {
        Write-Host "❌ Error: Unable to parse Python version. Found: '$pythonVersion'" -ForegroundColor Red
        exit 1
    }

    $requiredVersion = "3.8"
    if ([version]$pythonVersion -lt [version]$requiredVersion) {
        Write-Host "❌ Error: Python 3.8 or higher is required. Found: $pythonVersion" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Python version: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Error checking Python version: $_" -ForegroundColor Red
    exit 1
}

# Create virtual environment
if (-not $SkipVirtualEnv) {
    if (-not (Test-Path "venv")) {
        Write-Host "📦 Creating virtual environment..." -ForegroundColor Yellow
        python -m venv venv
    } else {
        Write-Host "✅ Virtual environment already exists" -ForegroundColor Green
    }
    
    # Activate virtual environment
    Write-Host "🔧 Activating virtual environment..." -ForegroundColor Yellow
    & "venv\Scripts\Activate.ps1"
}

# Upgrade pip
Write-Host "⬆️  Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install basic requirements
Write-Host "📚 Installing basic requirements..." -ForegroundColor Yellow
pip install -r requirements_basic.txt

# Install development requirements
Write-Host "🔧 Installing development requirements..." -ForegroundColor Yellow
pip install -r requirements.txt

# Install development tools
Write-Host "🛠️  Installing development tools..." -ForegroundColor Yellow
pip install pytest pytest-cov coverage black flake8

# Create necessary directories
Write-Host "📁 Creating necessary directories..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "downloads" | Out-Null
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
New-Item -ItemType Directory -Force -Path "templates" | Out-Null

# Create initial configuration files if they don't exist
if (-not (Test-Path "config.yaml")) {
    Write-Host "⚙️  Creating initial config.yaml..." -ForegroundColor Yellow
    if (Test-Path "config.yaml.example") {
        Copy-Item "config.yaml.example" "config.yaml"
    } else {
        "# Configuration file" | Out-File -FilePath "config.yaml" -Encoding UTF8
    }
}

if (-not (Test-Path ".env")) {
    Write-Host "🔐 Creating initial .env file..." -ForegroundColor Yellow
    @"
# Environment variables for secrets
# Add your credentials here
"@ | Out-File -FilePath ".env" -Encoding UTF8
}

Write-Host ""
Write-Host "🎉 Development environment setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Edit config.yaml with your settings" -ForegroundColor White
Write-Host "2. Edit .env with your credentials" -ForegroundColor White
Write-Host "3. Run: python run_newspaper.py --onboarding" -ForegroundColor White
Write-Host "4. Test: python run_newspaper.py --health" -ForegroundColor White
Write-Host "5. Start GUI: python gui_app.py" -ForegroundColor White
Write-Host ""
Write-Host "To activate the environment in the future:" -ForegroundColor Cyan
Write-Host "venv\Scripts\Activate.ps1" -ForegroundColor White