# FantaCalcio-AI Local Development Setup Guide

## 🎯 Complete Setup for Windows Development

This guide will help you set up the entire FantaCalcio-AI application on your local Windows machine for development, and prepare for deployment to Hetzner.

---

## 📋 Prerequisites

### Required Software
- **Python 3.11** (NOT 3.12, as per pyproject.toml)
- **PostgreSQL 16** (database)
- **Git** (version control)
- **VS Code** (already installed)

---

## 🔧 Step-by-Step Setup

### Step 1: Install PostgreSQL 16

1. **Download PostgreSQL 16 for Windows:**
   - Visit: https://www.postgresql.org/download/windows/
   - Download the installer from EnterpriseDB
   - Or use direct link: https://www.enterprisedb.com/downloads/postgres-postgresql-downloads

2. **Run the installer:**
   - Choose installation directory (default: `C:\Program Files\PostgreSQL\16`)
   - Set a **strong password** for the `postgres` superuser (remember this!)
   - Default port: `5432`
   - Locale: Default
   - Install Stack Builder: Optional (not needed)

3. **Verify installation:**
   ```powershell
   # Add PostgreSQL to PATH (if not automatic)
   $env:PATH += ";C:\Program Files\PostgreSQL\16\bin"
   
   # Test connection
   psql --version
   ```

### Step 2: Create the Database

1. **Open PowerShell as Administrator** and run:
   ```powershell
   # Connect to PostgreSQL
   psql -U postgres
   ```

2. **In the PostgreSQL prompt, create database and user:**
   ```sql
   -- Create database
   CREATE DATABASE fantacalcio_db;
   
   -- Create user with password
   CREATE USER fantacalcio_user WITH PASSWORD 'your_secure_password_here';
   
   -- Grant privileges
   GRANT ALL PRIVILEGES ON DATABASE fantacalcio_db TO fantacalcio_user;
   
   -- Connect to the database
   \c fantacalcio_db
   
   -- Grant schema privileges
   GRANT ALL ON SCHEMA public TO fantacalcio_user;
   
   -- Exit
   \q
   ```

3. **Test the connection:**
   ```powershell
   psql -U fantacalcio_user -d fantacalcio_db -h localhost
   ```

### Step 3: Set Up Python Environment

1. **Verify Python version:**
   ```powershell
   python --version  # Should show Python 3.11.x
   ```

2. **Create virtual environment:**
   ```powershell
   cd "c:\Users\Davide\VS-Code Solutions\FantaCalcio-AI\FantaCalcio-AI"
   
   # Create venv
   python -m venv venv
   
   # Activate it
   .\venv\Scripts\Activate.ps1
   ```
   
   > **Note:** If you get execution policy error, run:
   > ```powershell
   > Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   > ```

3. **Upgrade pip:**
   ```powershell
   python -m pip install --upgrade pip
   ```

### Step 4: Install Dependencies

1. **Install from requirements.txt:**
   ```powershell
   pip install -r requirements.txt
   ```

2. **Or use Poetry (alternative):**
   ```powershell
   pip install poetry
   poetry install
   ```

### Step 5: Configure Environment Variables

1. **Copy the example .env file:**
   ```powershell
   Copy-Item .env.example .env
   ```

2. **Edit `.env` file** with your settings:
   ```env
   # Database Configuration
   DATABASE_URL=postgresql://fantacalcio_user:your_secure_password_here@localhost:5432/fantacalcio_db
   
   # Session Security
   SESSION_SECRET=generate_a_random_secret_here_use_pwgen_or_openssl
   
   # OpenAI API (required for AI features)
   OPENAI_API_KEY=sk-your-openai-api-key-here
   OPENAI_MODEL=gpt-4o-mini
   OPENAI_TEMPERATURE=0.20
   OPENAI_MAX_TOKENS=600
   
   # HuggingFace (for embeddings)
   HUGGINGFACE_TOKEN=hf_your_huggingface_token_here
   
   # Stripe (optional, for Pro subscriptions)
   STRIPE_SECRET_KEY=sk_test_your_stripe_secret_key
   STRIPE_PUBLISHABLE_KEY=pk_test_your_stripe_public_key
   
   # Apify (optional, for web scraping)
   APIFY_API_TOKEN=your_apify_token_here
   
   # Application Settings
   ENVIRONMENT=development
   LOG_LEVEL=INFO
   HOST=127.0.0.1
   PORT=5000
   
   # Data Paths
   ROSTER_JSON_PATH=./season_roster.json
   CHROMA_PATH=./chroma_db
   CHROMA_DB_PATH=./chroma_db
   CHROMA_COLLECTION_NAME=fantacalcio_knowledge
   AGE_INDEX_PATH=./data/age_index.cleaned.json
   AGE_OVERRIDES_PATH=./data/age_overrides.json
   
   # Features
   ENABLE_WEB_FALLBACK=false
   SEASON_FILTER=2024-25
   REF_YEAR=2025
   ```

3. **Generate secure SESSION_SECRET:**
   ```powershell
   # Using Python
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

### Step 6: Initialize Database

1. **Run database initialization script:**
   ```powershell
   python init_db.py
   ```
   
   This will:
   - Create all required tables (users, user_leagues, subscriptions, oauth)
   - Set up proper indexes
   - Create an admin user for testing

2. **Verify tables were created:**
   ```powershell
   psql -U fantacalcio_user -d fantacalcio_db -c "\dt"
   ```

### Step 7: Prepare Data Directories

1. **Create required directories:**
   ```powershell
   # Create directories if they don't exist
   New-Item -ItemType Directory -Force -Path "./chroma_db"
   New-Item -ItemType Directory -Force -Path "./cache"
   New-Item -ItemType Directory -Force -Path "./data"
   New-Item -ItemType Directory -Force -Path "./static/assets"
   ```

2. **Check if season_roster.json exists:**
   ```powershell
   Test-Path "./season_roster.json"
   ```
   
   > **Note:** If this file doesn't exist, you'll need to run the ETL pipeline to fetch player data (see ETL Setup section below).

### Step 8: Verify Installation

1. **Run verification script:**
   ```powershell
   python verify_setup.py
   ```
   
   This checks:
   - Database connectivity
   - Required environment variables
   - Python dependencies
   - Data files existence
   - ChromaDB initialization

### Step 9: Run the Application

1. **Start the development server:**
   ```powershell
   python main.py
   ```
   
   You should see:
   ```
   Starting development server on port 5000 with debug=True
   * Running on http://127.0.0.1:5000
   ```

2. **Open your browser:**
   - Navigate to: http://localhost:5000
   - You should see the FantaCalcio-AI interface

3. **Create your first user:**
   - Click "Register" (or go to http://localhost:5000/auth/register)
   - Create an account
   - Log in and access the dashboard

---

## 🔄 ETL Setup (Data Collection)

### Initial Data Population

If you don't have `season_roster.json`, you need to populate data:

1. **Option A: Use Apify (Recommended - Professional scraping)**
   ```powershell
   # Requires APIFY_API_TOKEN in .env
   python etl_tm_serie_a_full.py
   ```

2. **Option B: Manual roster build**
   ```powershell
   python etl_build_roster.py
   ```

3. **Option C: Import existing data**
   - If you have a backup from Replit, copy it:
   ```powershell
   Copy-Item path\to\season_roster.json .\season_roster.json
   ```

### Populate ChromaDB Knowledge Base

```powershell
# Ingest documents into ChromaDB
python ingest_cli.py
```

---

## 🧪 Testing Your Setup

### Test 1: Database Connection
```powershell
python -c "from app import db; from sqlalchemy import text; db.session.execute(text('SELECT 1')); print('✅ Database connected')"
```

### Test 2: API Keys
```powershell
python -c "import os; from config import OPENAI_API_KEY; print('✅ OpenAI configured' if OPENAI_API_KEY else '❌ OpenAI key missing')"
```

### Test 3: Import All Modules
```powershell
python -c "from fantacalcio_assistant import FantacalcioAssistant; print('✅ All imports successful')"
```

### Test 4: Create Test User via Python
```python
# test_user.py
from app import app, db
from models import User

with app.app_context():
    # Create test user
    user = User(
        username='testuser',
        email='test@example.com',
        first_name='Test',
        last_name='User'
    )
    user.set_password('testpass123')
    
    db.session.add(user)
    db.session.commit()
    print(f"✅ Created user: {user.username}")
```

---

## 🐛 Common Issues & Solutions

### Issue 1: PostgreSQL Connection Failed
```
Error: could not connect to server
```
**Solution:**
- Check PostgreSQL service is running: `Get-Service -Name postgresql*`
- Start if needed: `Start-Service postgresql-x64-16`
- Verify connection: `psql -U postgres -c "SELECT version();"`

### Issue 2: Python Module Not Found
```
ModuleNotFoundError: No module named 'flask'
```
**Solution:**
- Ensure virtual environment is activated
- Reinstall dependencies: `pip install -r requirements.txt`

### Issue 3: ChromaDB Lock Error
```
Error: database is locked
```
**Solution:**
```powershell
# Remove lock files
Remove-Item -Path ".\chroma_db\chroma.sqlite3-wal" -ErrorAction SilentlyContinue
Remove-Item -Path ".\chroma_db\chroma.sqlite3-shm" -ErrorAction SilentlyContinue
```

### Issue 4: Port Already in Use
```
Error: Address already in use
```
**Solution:**
```powershell
# Find process using port 5000
Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | Select-Object OwningProcess
# Kill the process (replace PID)
Stop-Process -Id PID -Force

# Or use different port
$env:PORT=5001
python main.py
```

### Issue 5: Session Secret Missing
```
ValueError: SESSION_SECRET environment variable must be set
```
**Solution:**
- Ensure `.env` file exists and has `SESSION_SECRET` set
- Generate one: `python -c "import secrets; print(secrets.token_hex(32))"`

---

## 🚀 Deployment to Hetzner (Preview)

Once local development is working, here's the Hetzner deployment overview:

### Hetzner Server Setup
1. **Create Ubuntu 22.04 server** on Hetzner Cloud
2. **Install PostgreSQL 16** on server
3. **Install Python 3.11** and dependencies
4. **Set up Nginx** as reverse proxy
5. **Use systemd** for process management
6. **Configure SSL** with Let's Encrypt

### Deployment Steps (Coming Next)
```bash
# SSH to server
ssh root@your-hetzner-ip

# Install dependencies
apt update && apt install -y postgresql-16 python3.11 python3.11-venv nginx

# Clone repository
git clone <your-repo-url> /opt/fantacalcio-ai

# Set up application (similar to local steps)
# Configure systemd service
# Set up Nginx reverse proxy
```

> **Note:** Full Hetzner deployment guide will be created once local setup is verified.

---

## 📚 Next Steps After Setup

1. **Explore the Dashboard:** Log in and create your first league
2. **Test AI Assistant:** Ask questions like "Consigliami i migliori portieri"
3. **Run ETL Pipeline:** Populate with latest Serie A data
4. **Customize Rules:** Configure your league rules
5. **Review Code:** Familiarize yourself with the codebase

---

## 🆘 Need Help?

- Check logs in the console
- Run `python verify_setup.py` to diagnose issues
- Review error messages carefully
- Check PostgreSQL logs: `C:\Program Files\PostgreSQL\16\data\log\`

---

## 🔐 Security Notes for Production

When deploying to Hetzner:
- ✅ Use strong passwords for PostgreSQL
- ✅ Configure firewall rules (UFW)
- ✅ Enable SSL/TLS for database connections
- ✅ Use environment-specific secrets
- ✅ Set up automated backups
- ✅ Configure fail2ban for SSH protection
- ✅ Use Nginx rate limiting
