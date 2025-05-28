#!/bin/bash
# setup-oracle-demo.sh - Oracle Cloud Database Demo Setup for Linux/Mac

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get mode parameter (default to demo)
MODE=${1:-demo}

print_status "Setting up Oracle Cloud Database Demo Environment..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker and try again."
    exit 1
fi

# Create necessary directories
print_status "Creating directory structure..."
mkdir -p oracle-demo/init
mkdir -p oracle-wallets/demo
mkdir -p oracle-wallets/production

# Create demo wallet README files
print_status "Setting up demo wallet files..."

cat > oracle-wallets/demo/README.md << 'EOF'
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
EOF

cat > oracle-wallets/production/README.md << 'EOF'
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
EOF

case "$MODE" in
    "demo")
        print_status "Setting up DEMO mode..."
        
        # Backup current docker-compose if exists
        if [ -f "docker-compose.yml" ]; then
            cp docker-compose.yml docker-compose-backup.yml
            print_warning "Backed up existing docker-compose.yml to docker-compose-backup.yml"
        fi
        
        # Stop any running containers
        print_status "Stopping existing containers..."
        docker-compose down 2>/dev/null || true
        
        # Build and start demo environment
        print_status "Building and starting demo environment..."
        docker-compose up --build -d
        
        # Wait for Oracle to be ready
        print_status "Waiting for Oracle database to initialize (this may take a few minutes)..."
        
        max_attempts=30
        attempt=1
        oracle_ready=false
        
        while [ $attempt -le $max_attempts ]; do
            if docker logs oracle-demo 2>&1 | grep -q "DATABASE IS READY TO USE"; then
                print_success "Oracle database is ready!"
                oracle_ready=true
                break
            fi
            
            print_status "Waiting for Oracle... (attempt $attempt/$max_attempts)"
            sleep 10
            attempt=$((attempt + 1))
        done
        
        if [ "$oracle_ready" = false ]; then
            print_error "Oracle database failed to start within expected time"
            print_warning "Check logs with: docker logs oracle-demo"
            exit 1
        fi
        
        # Test database connectivity
        print_status "Testing database connectivity..."
        sleep 5
        
        if curl -s http://localhost:8082/db-health | grep -q '"status":"ok"'; then
            print_success "Database connectivity test passed!"
        else
            print_warning "Database connectivity test failed, but services are running"
            print_warning "Check logs with: docker logs langchain"
        fi
        
        # Show service status
        print_success "Demo environment is ready!"
        echo ""
        echo -e "${BLUE}📊 Services Available:${NC}"
        echo "  • LibreChat UI:     http://localhost:3100"
        echo "  • LangChain API:    http://localhost:8082"
        echo "  • Ollama API:       http://localhost:11434"
        echo "  • Oracle Database:  localhost:1521"
        echo "  • MongoDB:          localhost:27017"
        echo ""
        echo -e "${BLUE}🔧 Health Checks:${NC}"
        echo "  • Database Health:  curl http://localhost:8082/db-health"
        echo "  • API Health:       curl http://localhost:8082/health"
        echo ""
        echo -e "${BLUE}📝 Demo Credentials:${NC}"
        echo "  • Oracle System:    system/DemoPassword123"
        echo "  • Users Table:      users_reader/UsersTable123"
        echo "  • Orders Table:     orders_reader/OrdersTable123"
        echo "  • Products Table:   products_reader/ProductsTable123"
        echo "  • Analytics Table:  analytics_reader/AnalyticsTable123"
        ;;
        
    "production")
        print_status "Setting up PRODUCTION mode..."
        
        # Check if production wallet exists
        if [ ! -f "oracle-wallets/production/cwallet.sso" ]; then
            print_error "Production wallet files not found!"
            print_warning "Please place your Oracle Cloud wallet files in oracle-wallets/production/"
            print_warning "Then run: ./setup-oracle-demo.sh production"
            exit 1
        fi
        
        # Update environment for production
        if [ -f ".env.oracle" ]; then
            sed -i.bak 's/DEMO_MODE=true/DEMO_MODE=false/' .env.oracle
        fi
        
        print_warning "Production mode requires manual configuration of:"
        echo "  1. Oracle Cloud connection details in .env.oracle"
        echo "  2. Production table credentials"
        echo "  3. Wallet configuration"
        echo ""
        echo "Review .env.oracle and update production settings before deployment."
        ;;
        
    "stop")
        print_status "Stopping all services..."
        docker-compose down
        print_success "All services stopped"
        ;;
        
    "logs")
        echo -e "${BLUE}📋 Recent logs from all services:${NC}"
        docker-compose logs --tail=50
        ;;
        
    "reset")
        echo -n "This will remove all data and containers. Are you sure? (y/N): "
        read -r response
        if [ "$response" = "y" ] || [ "$response" = "Y" ]; then
            print_status "Resetting demo environment..."
            docker-compose down -v
            docker system prune -f
            print_success "Demo environment reset complete"
        else
            print_status "Reset cancelled"
        fi
        ;;
        
    "health")
        print_status "Checking service health..."
        echo ""
        
        # Check Docker
        if docker info > /dev/null 2>&1; then
            echo -e "✅ Docker: ${GREEN}Running${NC}"
        else
            echo -e "❌ Docker: ${RED}Not running${NC}"
        fi
        
        # Check services
        if docker-compose ps | grep -q "Up"; then
            echo -e "✅ Services: ${GREEN}Running${NC}"
            docker-compose ps
        else
            echo -e "❌ Services: ${RED}Not running${NC}"
        fi
        
        # Check Oracle health
        if curl -s http://localhost:8082/db-health > /dev/null; then
            DB_STATUS=$(curl -s http://localhost:8082/db-health | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
            if [ "$DB_STATUS" = "ok" ]; then
                echo -e "✅ Database: ${GREEN}Connected${NC}"
            else
                echo -e "❌ Database: ${RED}Disconnected${NC}"
            fi
        else
            echo -e "❌ Database: ${RED}API not responding${NC}"
        fi
        ;;
        
    *)
        echo "Usage: $0 [demo|production|stop|logs|reset|health]"
        echo ""
        echo "Commands:"
        echo "  demo        - Set up demo environment with local Oracle database"
        echo "  production  - Configure for production Oracle Cloud database"
        echo "  stop        - Stop all running services"
        echo "  logs        - Show recent logs from all services"
        echo "  reset       - Remove all containers and data (demo only)"
        echo "  health      - Check status of all services"
        echo ""
        echo "Default: demo"
        exit 1
        ;;
esac