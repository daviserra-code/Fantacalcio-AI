# FantaCalcio-AI Docker Setup Guide

## 🐳 Quick Start with Docker

This is the **recommended** way to run FantaCalcio-AI locally and deploy to Hetzner.

---

## 📋 Prerequisites

- **Docker Desktop** (Windows) or **Docker Engine** (Linux)
- **Docker Compose** (included with Docker Desktop)
- **Git** (optional, for cloning)

### Install Docker Desktop on Windows

1. Download from: https://www.docker.com/products/docker-desktop/
2. Install and restart your computer
3. Verify installation:
   ```powershell
   docker --version
   docker-compose --version
   ```

---

## 🚀 Local Development Setup (5 minutes)

### Step 1: Configure Environment Variables

```powershell
# Navigate to project directory
cd "c:\Users\Davide\VS-Code Solutions\FantaCalcio-AI\FantaCalcio-AI"

# Copy environment template
Copy-Item .env.docker .env

# Edit .env file with your credentials
notepad .env
```

**Required variables to set:**
```env
# Set a secure database password
DB_PASSWORD=my_secure_db_password_123

# Generate a random session secret
SESSION_SECRET=use_openssl_rand_hex_32_or_similar_random_string

# Add your OpenAI API key
OPENAI_API_KEY=sk-your-actual-openai-key

# Add your HuggingFace token
HUGGINGFACE_TOKEN=hf_your-actual-token
```

**Generate SESSION_SECRET:**
```powershell
# Option 1: Using Python
python -c "import secrets; print(secrets.token_hex(32))"

# Option 2: Using PowerShell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | % {[char]$_})
```

### Step 2: Start the Application

```powershell
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Or view specific service logs
docker-compose logs -f app
docker-compose logs -f postgres
```

### Step 3: Initialize Database

```powershell
# Run database initialization inside container
docker-compose exec app python init_db.py --create-admin

# Check database status
docker-compose exec app python init_db.py --status
```

### Step 4: Access the Application

- **Web Interface:** http://localhost:5000
- **Login with test user:**
  - Username: `testuser`
  - Password: `testpass123`

---

## 🛠️ Docker Commands Cheat Sheet

### Service Management
```powershell
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart a service
docker-compose restart app

# View running containers
docker-compose ps

# View logs (all services)
docker-compose logs -f

# View logs (specific service)
docker-compose logs -f app
docker-compose logs -f postgres
```

### Database Management
```powershell
# Connect to PostgreSQL
docker-compose exec postgres psql -U fantacalcio_user -d fantacalcio_db

# Create database backup
docker-compose exec postgres pg_dump -U fantacalcio_user fantacalcio_db > backup_$(date +%Y%m%d).sql

# Restore database backup
docker-compose exec -T postgres psql -U fantacalcio_user -d fantacalcio_db < backup.sql

# Check database size
docker-compose exec postgres psql -U fantacalcio_user -d fantacalcio_db -c "\l+"
```

### Application Management
```powershell
# Execute commands in app container
docker-compose exec app python init_db.py --status

# Run ETL pipeline
docker-compose exec app python etl_build_roster.py

# Access app shell
docker-compose exec app bash

# View app environment variables
docker-compose exec app env | grep -i openai
```

### Rebuilding After Code Changes
```powershell
# Rebuild and restart app
docker-compose up -d --build app

# Force complete rebuild
docker-compose build --no-cache app
docker-compose up -d app
```

### Cleanup
```powershell
# Stop and remove containers
docker-compose down

# Remove volumes (WARNING: deletes data!)
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Clean up unused Docker resources
docker system prune -a
```

---

## 🔧 Development Workflow

### Option 1: Quick Testing (Rebuild Container)
```powershell
# Make code changes, then:
docker-compose up -d --build app
docker-compose logs -f app
```

### Option 2: Live Development (Volume Mount)

Edit `docker-compose.yml` and uncomment the source volume:
```yaml
volumes:
  - .:/app  # Uncomment this line
```

Then:
```powershell
docker-compose up -d
# Changes are reflected immediately (Flask debug mode)
```

---

## 📊 Monitoring & Debugging

### Check Service Health
```powershell
# View container status
docker-compose ps

# Check health status
docker inspect fantacalcio-app | grep -A 10 Health

# Test application endpoint
curl http://localhost:5000/ready
```

### View Resource Usage
```powershell
# Container stats
docker stats

# Specific container
docker stats fantacalcio-app fantacalcio-postgres
```

### Debug Container Issues
```powershell
# View full logs
docker-compose logs --tail=100 app

# Access container shell
docker-compose exec app bash

# Check Python packages
docker-compose exec app pip list

# Test database connection
docker-compose exec app python -c "from app import db; from sqlalchemy import text; db.session.execute(text('SELECT 1')); print('✅ DB Connected')"
```

---

## 🚀 Hetzner Deployment Guide

### Prerequisites on Hetzner Server

1. **Create Ubuntu 22.04 server** on Hetzner Cloud
2. **SSH into server:**
   ```bash
   ssh root@your-server-ip
   ```

3. **Install Docker:**
   ```bash
   # Update system
   apt update && apt upgrade -y
   
   # Install Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sh get-docker.sh
   
   # Install Docker Compose
   apt install -y docker-compose-plugin
   
   # Verify installation
   docker --version
   docker compose version
   ```

### Deploy Application

1. **Clone repository:**
   ```bash
   cd /opt
   git clone https://github.com/your-username/fantacalcio-ai.git
   cd fantacalcio-ai
   ```

2. **Configure environment:**
   ```bash
   # Copy and edit environment file
   cp .env.docker .env
   nano .env
   
   # Set production values:
   # - Strong DB_PASSWORD
   # - Secure SESSION_SECRET
   # - Production API keys
   # - ENVIRONMENT=production
   ```

3. **Start services:**
   ```bash
   docker compose up -d
   ```

4. **Initialize database:**
   ```bash
   docker compose exec app python init_db.py --create-admin
   ```

5. **Set up Nginx reverse proxy (optional):**
   ```bash
   # Enable production profile
   docker compose --profile production up -d
   ```

### Domain & SSL Setup

1. **Point domain to server:**
   - Add A record: `fantacalcio.yourdomain.com` → `your-server-ip`

2. **Install Certbot (if using Nginx):**
   ```bash
   apt install -y certbot python3-certbot-nginx
   certbot --nginx -d fantacalcio.yourdomain.com
   ```

### Automatic Backups

Create backup script `/opt/backup-fantacalcio.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/opt/fantacalcio-backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
docker compose exec -T postgres pg_dump -U fantacalcio_user fantacalcio_db > "$BACKUP_DIR/db_$DATE.sql"

# Backup volumes
docker run --rm -v fantacalcio-ai_chroma_data:/data -v $BACKUP_DIR:/backup alpine tar czf /backup/chroma_$DATE.tar.gz -C /data .

# Keep only last 7 days
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

echo "✅ Backup completed: $DATE"
```

Set up cron job:
```bash
chmod +x /opt/backup-fantacalcio.sh
crontab -e

# Add this line for daily backup at 2 AM
0 2 * * * /opt/backup-fantacalcio.sh >> /var/log/fantacalcio-backup.log 2>&1
```

### Systemd Service (Auto-restart)

Create `/etc/systemd/system/fantacalcio.service`:
```ini
[Unit]
Description=FantaCalcio-AI Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/fantacalcio-ai
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable auto-start:
```bash
systemctl daemon-reload
systemctl enable fantacalcio
systemctl start fantacalcio
```

---

## 🔐 Security Best Practices

### For Production:
- ✅ Use strong, unique passwords
- ✅ Change default credentials immediately
- ✅ Enable UFW firewall
- ✅ Use SSL/TLS (Let's Encrypt)
- ✅ Keep Docker images updated
- ✅ Regular automated backups
- ✅ Monitor logs for suspicious activity
- ✅ Limit database port exposure (remove `ports: 5432` from docker-compose.yml)

### Firewall Setup (Hetzner):
```bash
# Enable UFW
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw enable

# Block direct database access from outside
# (Already handled by not exposing port in docker-compose)
```

---

## 🐛 Troubleshooting

### Port Already in Use
```powershell
# Change port in .env
APP_PORT=5001

# Or stop conflicting service
netstat -ano | findstr :5000
Stop-Process -Id PID -Force
```

### Database Connection Failed
```powershell
# Check postgres is running
docker-compose ps postgres

# View postgres logs
docker-compose logs postgres

# Restart postgres
docker-compose restart postgres
```

### App Won't Start
```powershell
# Check logs
docker-compose logs app

# Rebuild container
docker-compose up -d --build --force-recreate app

# Check environment variables
docker-compose exec app env | grep DATABASE_URL
```

### Out of Disk Space
```powershell
# Check Docker disk usage
docker system df

# Clean up
docker system prune -a --volumes

# Check specific volumes
docker volume ls
```

---

## 📚 Next Steps

1. ✅ Start the application: `docker-compose up -d`
2. ✅ Initialize database: `docker-compose exec app python init_db.py`
3. ✅ Access at http://localhost:5000
4. ✅ Run ETL to populate data: `docker-compose exec app python etl_build_roster.py`
5. ✅ Deploy to Hetzner (see Hetzner section above)

---

## 🆘 Need Help?

- Check logs: `docker-compose logs -f`
- Verify setup: `docker-compose exec app python verify_setup.py`
- Database status: `docker-compose exec app python init_db.py --status`
- Container status: `docker-compose ps`
