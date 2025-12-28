# FantaCalcio-AI - Quick Start Guide

## 🚀 Get Started in 3 Steps

### Step 1: Configure Environment
```powershell
cd "c:\Users\Davide\VS-Code Solutions\FantaCalcio-AI\FantaCalcio-AI"
Copy-Item .env.docker .env
notepad .env  # Edit with your API keys
```

### Step 2: Start with Docker
```powershell
docker-compose up -d
docker-compose logs -f
```

### Step 3: Initialize Database
```powershell
docker-compose exec app python init_db.py
```

**Access at:** http://localhost:5000

---

## 📚 Documentation Files

- **[DOCKER_SETUP.md](DOCKER_SETUP.md)** - Complete Docker guide (RECOMMENDED)
- **[LOCAL_SETUP_GUIDE.md](LOCAL_SETUP_GUIDE.md)** - Manual setup without Docker
- **[replit.md](replit.md)** - Application architecture overview

---

## 🐳 Docker Commands Quick Reference

```powershell
# Start services
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop services
docker-compose down

# Database backup
docker-compose exec postgres pg_dump -U fantacalcio_user fantacalcio_db > backup.sql

# Run ETL pipeline
docker-compose exec app python etl_build_roster.py

# Verify setup
docker-compose exec app python verify_setup.py

# Database status
docker-compose exec app python init_db.py --status
```

---

## 🔑 Required Environment Variables

```env
DB_PASSWORD=your_secure_password
SESSION_SECRET=generate_random_32_chars
OPENAI_API_KEY=sk-your-key-here
HUGGINGFACE_TOKEN=hf_your-token
```

Generate SESSION_SECRET:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 🚀 Deploy to Hetzner

```bash
# On Hetzner server
git clone your-repo /opt/fantacalcio-ai
cd /opt/fantacalcio-ai

# Configure
cp .env.docker .env
nano .env  # Set production values

# Start
docker compose up -d

# Initialize
docker compose exec app python init_db.py --create-admin
```

See [DOCKER_SETUP.md](DOCKER_SETUP.md) for complete deployment guide.

---

## 🐛 Troubleshooting

**Container won't start:**
```powershell
docker-compose logs app
docker-compose up -d --build --force-recreate app
```

**Database connection failed:**
```powershell
docker-compose restart postgres
docker-compose logs postgres
```

**Port conflict:**
```powershell
# Edit .env and change APP_PORT
APP_PORT=5001
docker-compose up -d
```

---

## 📞 Support

- Check logs: `docker-compose logs -f`
- Verify setup: `docker-compose exec app python verify_setup.py`
- Database status: `docker-compose exec app python init_db.py --status`

---

**Created by:** AI Assistant  
**Date:** December 27, 2025  
**Version:** 1.0.0
