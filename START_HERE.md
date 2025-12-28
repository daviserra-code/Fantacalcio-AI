# ⚡ FantaCalcio-AI - Ready to Start!

## ✅ What I've Set Up For You

Your environment is **almost ready**! Here's what's configured:

### Files Created:
1. ✅ **`.env`** - Environment file with secure defaults
2. ✅ **`docker-compose.yml`** - Complete Docker setup
3. ✅ **`Dockerfile`** - Application container
4. ✅ **`init_db.py`** - Database initialization
5. ✅ **`verify_setup.py`** - Setup verification
6. ✅ **`quickstart.ps1`** - PowerShell quick start script

### Pre-configured:
- ✅ Database credentials (Docker managed)
- ✅ Session secret (auto-generated)
- ✅ Application settings
- ✅ Data paths
- ✅ All required services

---

## 🔑 You Only Need 2 Things

### 1. OpenAI API Key
**Where:** [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)

Add to `.env`:
```env
OPENAI_API_KEY=sk-your-actual-key-here
```

### 2. HuggingFace Token
**Where:** [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

Add to `.env`:
```env
HUGGINGFACE_TOKEN=hf_your-actual-token-here
HF_TOKEN=hf_your-actual-token-here
```

---

## 🚀 Quick Start (3 Options)

### Option 1: PowerShell Script (Easiest)
```powershell
.\quickstart.ps1
```
This interactive script will guide you through everything!

### Option 2: Manual Docker Start
```powershell
# 1. Edit .env to add your API keys
notepad .env

# 2. Start Docker
docker-compose up -d

# 3. Initialize database
docker-compose exec app python init_db.py

# 4. Visit
# http://localhost:5000
```

### Option 3: Python Setup Helper
```powershell
# Interactive configuration helper
python setup_env.py

# Then start Docker
docker-compose up -d
```

---

## 📋 What Happens When You Start

1. **PostgreSQL 16** starts with pre-configured database
2. **Python app** builds and connects to database
3. **Tables created** automatically (users, leagues, subscriptions)
4. **Test user** created for immediate testing
5. **Web interface** available at http://localhost:5000

---

## 🎯 First Login

After starting, you can:

**Option A: Register new account**
- Go to http://localhost:5000
- Click "Register"
- Create your account

**Option B: Use test account**
- Username: `testuser`
- Password: `testpass123`

---

## 🔍 Verify Everything Works

```powershell
# Check all containers are running
docker-compose ps

# View application logs
docker-compose logs -f app

# Verify environment
docker-compose exec app python verify_setup.py

# Check database
docker-compose exec app python init_db.py --status
```

---

## 📊 Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| Docker Setup | ✅ Complete | docker-compose.yml ready |
| Database Config | ✅ Complete | PostgreSQL pre-configured |
| Session Secret | ✅ Generated | Secure 256-bit key |
| .env File | ⚠️ Needs API Keys | Add OpenAI + HuggingFace |
| Application | ✅ Ready | All dependencies configured |

---

## 🔧 Optional: Add More Services

### Stripe (Pro Subscriptions)
```env
STRIPE_SECRET_KEY=sk_test_your_key
STRIPE_PUBLISHABLE_KEY=pk_test_your_key
```

### Apify (Web Scraping)
```env
APIFY_API_TOKEN=apfy_your_token
```

---

## 🌐 Deploy to Hetzner (Later)

Same Docker setup works on Hetzner! Just:
```bash
# On server
git clone your-repo /opt/fantacalcio-ai
cd /opt/fantacalcio-ai

# Configure .env with production values
nano .env

# Start
docker compose up -d
```

Full guide in [DOCKER_SETUP.md](DOCKER_SETUP.md)

---

## 🆘 Quick Troubleshooting

**Can't find API keys?**
- Check your existing AI projects
- Look in other .env files
- Create new ones (links above)

**Docker not starting?**
```powershell
docker system prune -a
docker-compose up -d --build
```

**Need help?**
```powershell
docker-compose logs -f
```

---

## 📞 Next Steps

1. **Add your API keys to `.env`**
2. **Run `.\quickstart.ps1`** or `docker-compose up -d`
3. **Visit http://localhost:5000**
4. **Start building your fantasy team! ⚽**

---

**Ready?** Just add those 2 API keys and run `.\quickstart.ps1`! 🚀
