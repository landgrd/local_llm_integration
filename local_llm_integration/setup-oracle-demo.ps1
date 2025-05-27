# setup-oracle-demo.ps1 - Oracle Cloud Database Demo Setup for Windows

param(
    [string]$Mode = "demo"
)

function Write-Status {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

Write-Status "Setting up Oracle Cloud Database Demo Environment..."

# Check if Docker is running
try {
    docker info | Out-Null
    Write-Status "Docker is running"
}
catch {
    Write-Error "Docker is not running. Please start Docker Desktop and try again."
    exit 1
}

# Create necessary directories
Write-Status "Creating directory structure..."
$directories = @(
    "oracle-demo\init",
    "oracle-wallets\demo", 
    "oracle-wallets\production"
)

foreach ($dir in $directories) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Status "Created directory: $dir"
    }
}

# Create demo wallet README files
Write-Status "Setting up demo wallet files..."

$demoWalletReadme = @"
# Demo Wallet Directory

This directory contains placeholder wallet files for demo mode.
In production, place your actual Oracle Cloud wallet files here:

- cwallet.sso
- ewallet.p12
- keystore.jks
- ojdbc.properties
- sqlnet.ora
- tnsnames.ora
- truststore.jks

For demo mode, these files are not needed as we connect directly to the demo Oracle container.
"@

$prodWalletReadme = @"
# Production Wallet Directory

Place your Oracle Cloud Database wallet files here for production deployment:

1. Download wallet from Oracle Cloud Console
2. Extract all files to this directory
3. Update .env.oracle with production settings
4. Set DEMO_MODE=false

Required files:
- cwallet.sso
- ewallet.p12
- keystore.jks
- ojdbc.properties
- sqlnet.ora
- tnsnames.ora
- truststore.jks
"@

$demoWalletReadme | Out-File -FilePath "oracle-wallets\demo\README.md" -Encoding UTF8
$prodWalletReadme | Out-File -FilePath "oracle-wallets\production\README.md" -Encoding UTF8

if ($Mode -eq "demo") {
    Write-Status "Setting up DEMO mode..."
    
    # Backup current docker-compose if exists
    if (Test-Path "docker-compose.yml") {
        Copy-Item "docker-compose.yml" "docker-compose-backup.yml"
        Write-Warning "Backed up existing docker-compose.yml to docker-compose-backup.yml"
    }
    
    # Stop any running containers
    Write-Status "Stopping existing containers..."
    try {
        docker-compose down 2>$null
    }
    catch {
        # Ignore errors if no containers are running
    }
    
    # Build and start demo environment
    Write-Status "Building and starting demo environment..."
    docker-compose up --build -d
    
    # Wait for Oracle to be ready
    Write-Status "Waiting for Oracle database to initialize (this may take a few minutes)..."
    
    $maxAttempts = 30
    $attempt = 1
    $oracleReady = $false
    
    while ($attempt -le $maxAttempts -and !$oracleReady) {
        try {
            $logs = docker logs oracle-demo 2>&1
            if ($logs -match "DATABASE IS READY TO USE") {
                Write-Success "Oracle database is ready!"
                $oracleReady = $true
                break
            }
        }
        catch {
            # Continue waiting
        }
        
        Write-Status "Waiting for Oracle... (attempt $attempt/$maxAttempts)"
        Start-Sleep -Seconds 10
        $attempt++
    }
    
    if (!$oracleReady) {
        Write-Error "Oracle database failed to start within expected time"
        Write-Warning "Check logs with: docker logs oracle-demo"
        exit 1
    }
    
    # Test database connectivity
    Write-Status "Testing database connectivity..."
    Start-Sleep -Seconds 5
    
    try {
        $healthCheck = Invoke-RestMethod -Uri "http://localhost:8082/db-health" -TimeoutSec 10
        if ($healthCheck.status -eq "ok") {
            Write-Success "Database connectivity test passed!"
        }
        else {
            Write-Warning "Database connectivity test failed, but services are running"
        }
    }
    catch {
        Write-Warning "Database connectivity test failed, but services are running"
        Write-Warning "Check logs with: docker logs langchain"
    }
    
    # Show service status
    Write-Success "Demo environment is ready!"
    Write-Host ""
    Write-Host "📊 Services Available:" -ForegroundColor Cyan
    Write-Host "  • LibreChat UI:     http://localhost:3100"
    Write-Host "  • LangChain API:    http://localhost:8082"
    Write-Host "  • Ollama API:       http://localhost:11434"
    Write-Host "  • Oracle Database:  localhost:1521"
    Write-Host "  • MongoDB:          localhost:27017"
    Write-Host ""
    Write-Host "🔧 Health Checks:" -ForegroundColor Cyan
    Write-Host "  • Database Health:  Invoke-RestMethod http://localhost:8082/db-health"
    Write-Host "  • API Health:       Invoke-RestMethod http://localhost:8082/health"
    Write-Host ""
    Write-Host "📝 Demo Credentials:" -ForegroundColor Cyan
    Write-Host "  • Oracle System:    system/DemoPassword123"
    Write-Host "  • Users Table:      users_reader/UsersTable123"
    Write-Host "  • Orders Table:     orders_reader/OrdersTable123"
    Write-Host "  • Products Table:   products_reader/ProductsTable123"
    Write-Host "  • Analytics Table:  analytics_reader/AnalyticsTable123"
}
elseif ($Mode -eq "production") {
    Write-Status "Setting up PRODUCTION mode..."
    
    # Check if production wallet exists
    if (!(Test-Path "oracle-wallets\production\cwallet.sso")) {
        Write-Error "Production wallet files not found!"
        Write-Warning "Please place your Oracle Cloud wallet files in oracle-wallets\production\"
        Write-Warning "Then run: .\setup-oracle-demo.ps1 production"
        exit 1
    }
    
    # Update environment for production
    if (Test-Path ".env.oracle") {
        (Get-Content ".env.oracle") -replace "DEMO_MODE=true", "DEMO_MODE=false" | Set-Content ".env.oracle"
    }
    
    Write-Warning "Production mode requires manual configuration of:"
    Write-Host "  1. Oracle Cloud connection details in .env.oracle"
    Write-Host "  2. Production table credentials"
    Write-Host "  3. Wallet configuration"
    Write-Host ""
    Write-Host "Review .env.oracle and update production settings before deployment."
}
elseif ($Mode -eq "stop") {
    Write-Status "Stopping all services..."
    docker-compose down
    Write-Success "All services stopped"
}
elseif ($Mode -eq "logs") {
    Write-Host "📋 Recent logs from all services:" -ForegroundColor Cyan
    docker-compose logs --tail=50
}
elseif ($Mode -eq "reset") {
    $response = Read-Host "This will remove all data and containers. Are you sure? (y/N)"
    if ($response -eq "y" -or $response -eq "Y") {
        Write-Status "Resetting demo environment..."
        docker-compose down -v
        docker system prune -f
        Write-Success "Demo environment reset complete"
    }
    else {
        Write-Status "Reset cancelled"
    }
}
else {
    Write-Host "Usage: .\setup-oracle-demo.ps1 [demo|production|stop|logs|reset]"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  demo        - Set up demo environment with local Oracle database"
    Write-Host "  production  - Configure for production Oracle Cloud database"
    Write-Host "  stop        - Stop all running services"
    Write-Host "  logs        - Show recent logs from all services"
    Write-Host "  reset       - Remove all containers and data (demo only)"
    Write-Host ""
    Write-Host "Default: demo"
    exit 1
}