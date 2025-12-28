# Quick Setup Script for FantaCalcio-AI
# Run this in PowerShell to get started quickly

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  FantaCalcio-AI Quick Setup" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check Docker
Write-Host "1️⃣  Checking Docker..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version
    Write-Host "   ✅ Docker installed: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Docker not found! Please install Docker Desktop" -ForegroundColor Red
    Write-Host "      Download from: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
    exit 1
}

# Check .env file
Write-Host "`n2️⃣  Checking .env configuration..." -ForegroundColor Yellow
if (Test-Path .env) {
    Write-Host "   ✅ .env file found" -ForegroundColor Green
    
    # Check for API keys
    $envContent = Get-Content .env -Raw
    
    $needsOpenAI = $envContent -match 'OPENAI_API_KEY=\s*$' -or $envContent -notmatch 'OPENAI_API_KEY='
    $needsHF = $envContent -match 'HUGGINGFACE_TOKEN=\s*$' -or $envContent -notmatch 'HUGGINGFACE_TOKEN='
    
    if ($needsOpenAI -or $needsHF) {
        Write-Host "   ⚠️  API keys need to be configured" -ForegroundColor Yellow
        Write-Host ""
        
        if ($needsOpenAI) {
            Write-Host "   📝 Missing: OPENAI_API_KEY" -ForegroundColor Red
            Write-Host "      Get from: https://platform.openai.com/api-keys" -ForegroundColor Cyan
        }
        
        if ($needsHF) {
            Write-Host "   📝 Missing: HUGGINGFACE_TOKEN" -ForegroundColor Red
            Write-Host "      Get from: https://huggingface.co/settings/tokens" -ForegroundColor Cyan
        }
        
        Write-Host ""
        $edit = Read-Host "   Would you like to edit .env now? (y/n)"
        if ($edit -eq 'y') {
            notepad .env
            Write-Host "   Please save .env and run this script again" -ForegroundColor Yellow
            exit 0
        }
    } else {
        Write-Host "   ✅ API keys configured" -ForegroundColor Green
    }
} else {
    Write-Host "   ❌ .env file not found!" -ForegroundColor Red
    exit 1
}

# Offer to start Docker
Write-Host "`n3️⃣  Ready to start services" -ForegroundColor Yellow
$start = Read-Host "   Start Docker containers? (y/n)"

if ($start -eq 'y') {
    Write-Host "`n   🐳 Starting Docker containers..." -ForegroundColor Cyan
    docker-compose up -d
    
    Write-Host "`n   ⏳ Waiting for services to be ready..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
    
    Write-Host "`n4️⃣  Initializing database..." -ForegroundColor Yellow
    $init = Read-Host "   Initialize database with test user? (y/n)"
    
    if ($init -eq 'y') {
        docker-compose exec app python init_db.py
    }
    
    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host "  ✅ Setup Complete!" -ForegroundColor Green
    Write-Host "========================================`n" -ForegroundColor Green
    
    Write-Host "🌐 Application running at: http://localhost:5000" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "📋 Useful commands:" -ForegroundColor Yellow
    Write-Host "   docker-compose logs -f app      # View logs"
    Write-Host "   docker-compose ps               # Check status"
    Write-Host "   docker-compose down             # Stop services"
    Write-Host "   docker-compose restart app      # Restart app"
    Write-Host ""
    
    # Try to open browser
    $openBrowser = Read-Host "Open browser? (y/n)"
    if ($openBrowser -eq 'y') {
        Start-Process "http://localhost:5000"
    }
} else {
    Write-Host "`n   ℹ️  To start manually, run: docker-compose up -d" -ForegroundColor Cyan
}

Write-Host ""
