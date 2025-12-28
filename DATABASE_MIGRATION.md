# Database Migration Guide - Xeon PostgreSQL to Local Docker

## 📊 Current Status

Your local Docker database is **initialized but empty**:
- ✅ Tables created (users, leagues, subscriptions)
- ⚠️ Only 1 test user
- ⚠️ No production data yet

---

## 🔄 Migration Options

### Option 1: Full Data Export/Import (Recommended)

This creates a complete backup from Xeon and restores it locally.

#### On Your Xeon Server (SSH):

```bash
# 1. Create backup
pg_dump -U fantacalcio_user -h localhost fantacalcio_db > fantacalcio_backup.sql

# 2. Check backup size
ls -lh fantacalcio_backup.sql

# 3. Compress for faster transfer (optional)
gzip fantacalcio_backup.sql
```

#### On Your Windows Machine:

```powershell
# 1. Download backup from Xeon
scp user@xeon-ip:/path/to/fantacalcio_backup.sql ./

# 2. Import into local Docker database
Get-Content fantacalcio_backup.sql | docker-compose exec -T postgres psql -U fantacalcio_user -d fantacalcio_db

# 3. Verify import
docker-compose exec app python init_db.py --status
```

---

### Option 2: Tables-Only Export (Schema without data)

If you just want the structure without data:

```bash
# On Xeon server
pg_dump -U fantacalcio_user -h localhost --schema-only fantacalcio_db > schema_only.sql

# On Windows
Get-Content schema_only.sql | docker-compose exec -T postgres psql -U fantacalcio_user -d fantacalcio_db
```

---

### Option 3: Specific Tables Only

Export only certain tables:

```bash
# On Xeon server - export only users and leagues
pg_dump -U fantacalcio_user -h localhost -t users -t user_leagues -t subscriptions fantacalcio_db > tables_only.sql

# On Windows
Get-Content tables_only.sql | docker-compose exec -T postgres psql -U fantacalcio_user -d fantacalcio_db
```

---

### Option 4: Direct Connection (Testing Only)

Connect your local app directly to Xeon database without migration:

#### On Xeon Server:

```bash
# 1. Edit PostgreSQL config to allow remote connections
sudo nano /etc/postgresql/16/main/postgresql.conf

# Change:
listen_addresses = '*'  # or your local IP

# 2. Edit access control
sudo nano /etc/postgresql/16/main/pg_hba.conf

# Add line (replace with your IP):
host    fantacalcio_db    fantacalcio_user    192.168.1.0/24    md5

# 3. Restart PostgreSQL
sudo systemctl restart postgresql

# 4. Allow firewall
sudo ufw allow 5432/tcp
```

#### On Windows (.env file):

```env
# Change DATABASE_URL to point to Xeon
DATABASE_URL=postgresql://fantacalcio_user:password@xeon-server-ip:5432/fantacalcio_db
```

**⚠️ Security Warning:** Not recommended for production! Use only for testing.

---

## 🚀 Quick Migration (PowerShell Script)

Run the interactive helper:

```powershell
.\migrate_database.ps1
```

This script guides you through the migration process.

---

## 📝 Manual Migration Steps

### 1. Prepare Xeon Server

```bash
# SSH to Xeon
ssh user@xeon-ip

# Create backup directory
mkdir -p ~/db_backups

# Export database
pg_dump -U fantacalcio_user -d fantacalcio_db > ~/db_backups/fantacalcio_$(date +%Y%m%d).sql

# Check backup
ls -lh ~/db_backups/
```

### 2. Transfer to Windows

```powershell
# Download backup
scp user@xeon-ip:~/db_backups/fantacalcio_*.sql ./

# Or use WinSCP, FileZilla, etc.
```

### 3. Import to Docker

```powershell
# Stop app container (optional, to avoid conflicts)
docker-compose stop app

# Import backup
Get-Content fantacalcio_20251227.sql | docker-compose exec -T postgres psql -U fantacalcio_user -d fantacalcio_db

# If you get errors about existing tables, drop them first:
docker-compose exec postgres psql -U fantacalcio_user -d fantacalcio_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Then import again
Get-Content fantacalcio_20251227.sql | docker-compose exec -T postgres psql -U fantacalcio_user -d fantacalcio_db

# Restart app
docker-compose up -d app
```

### 4. Verify Migration

```powershell
# Check database status
docker-compose exec app python init_db.py --status

# Test login with your existing users
# Visit: http://localhost:5000
```

---

## 🔍 Troubleshooting

### "Role does not exist" error

```powershell
# Create user first
docker-compose exec postgres psql -U fantacalcio_user -d postgres -c "CREATE USER fantacalcio_user WITH PASSWORD 'fantacalcio2025secure!';"
```

### "Database does not exist" error

```powershell
# Create database
docker-compose exec postgres psql -U postgres -c "CREATE DATABASE fantacalcio_db OWNER fantacalcio_user;"
```

### Import hangs or is slow

```powershell
# Use file instead of pipe
docker cp fantacalcio_backup.sql fantacalcio-postgres:/tmp/
docker-compose exec postgres psql -U fantacalcio_user -d fantacalcio_db -f /tmp/fantacalcio_backup.sql
```

### Encoding issues

```bash
# On Xeon, export with encoding
pg_dump -U fantacalcio_user -d fantacalcio_db --encoding=UTF8 > backup.sql
```

---

## 🎯 Recommended Workflow

For **development**:
1. ✅ Export full backup from Xeon
2. ✅ Import to local Docker
3. ✅ Work locally
4. ✅ Test changes
5. ✅ Deploy to Xeon when ready

For **testing connection**:
1. ✅ Use Option 4 (direct connection) temporarily
2. ⚠️ Switch back to local Docker for development

---

## 📞 Quick Commands Reference

```powershell
# Check local database status
docker-compose exec app python init_db.py --status

# Import backup
Get-Content backup.sql | docker-compose exec -T postgres psql -U fantacalcio_user -d fantacalcio_db

# Connect to local database
docker-compose exec postgres psql -U fantacalcio_user -d fantacalcio_db

# Reset local database
docker-compose exec postgres psql -U fantacalcio_user -d fantacalcio_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker-compose exec app python init_db.py --create-admin

# View database size
docker-compose exec postgres psql -U fantacalcio_user -d fantacalcio_db -c "\l+"

# List all tables
docker-compose exec postgres psql -U fantacalcio_user -d fantacalcio_db -c "\dt"

# Count records in each table
docker-compose exec postgres psql -U fantacalcio_user -d fantacalcio_db -c "SELECT 'users' as table, COUNT(*) FROM users UNION SELECT 'leagues', COUNT(*) FROM user_leagues UNION SELECT 'subscriptions', COUNT(*) FROM subscriptions;"
```

---

## 🎉 After Successful Migration

Your local environment will have:
- ✅ All production users
- ✅ All leagues and configurations  
- ✅ All subscriptions
- ✅ Complete data for development

You can now develop and test locally without affecting production!
