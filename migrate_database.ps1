# Database Migration Script - From Xeon to Local Docker
# This guide helps you export data from your production Xeon PostgreSQL and import it locally

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Database Migration Helper" -ForegroundColor Cyan  
Write-Host "  Xeon → Local Docker PostgreSQL" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Configuration
$REMOTE_HOST = "your-xeon-server-ip"  # Change this to your Xeon server IP
$REMOTE_USER = "fantacalcio_user"     # Your PostgreSQL user on Xeon
$REMOTE_DB = "fantacalcio_db"         # Your database name on Xeon
$BACKUP_FILE = "xeon_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').sql"

Write-Host "📋 Migration Options:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Export from Xeon and import to Docker (recommended)" -ForegroundColor Green
Write-Host "2. Direct connection to Xeon for testing" -ForegroundColor Yellow
Write-Host "3. Create empty database with schema only" -ForegroundColor Cyan
Write-Host ""

$choice = Read-Host "Select option (1-3)"

switch ($choice) {
    "1" {
        Write-Host "`n📤 Option 1: Export & Import" -ForegroundColor Green
        Write-Host "=" * 60
        
        Write-Host "`nStep 1: Export from Xeon Server" -ForegroundColor Yellow
        Write-Host "Run this command on your Xeon server (via SSH):" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "pg_dump -U $REMOTE_USER -h localhost $REMOTE_DB > ~/fantacalcio_backup.sql" -ForegroundColor White
        Write-Host ""
        Write-Host "Then download the backup file:" -ForegroundColor Cyan
        Write-Host "scp user@${REMOTE_HOST}:~/fantacalcio_backup.sql ./$BACKUP_FILE" -ForegroundColor White
        Write-Host ""
        
        $hasBackup = Read-Host "Do you have the backup file ready? (y/n)"
        
        if ($hasBackup -eq "y") {
            $backupPath = Read-Host "Enter path to backup SQL file"
            
            if (Test-Path $backupPath) {
                Write-Host "`n📥 Importing backup to local Docker database..." -ForegroundColor Green
                
                # Import into Docker PostgreSQL
                Get-Content $backupPath | docker-compose exec -T postgres psql -U fantacalcio_user -d fantacalcio_db
                
                Write-Host "`n✅ Import completed!" -ForegroundColor Green
                Write-Host "Checking imported data..." -ForegroundColor Yellow
                
                docker-compose exec app python init_db.py --status
            } else {
                Write-Host "`n❌ Backup file not found: $backupPath" -ForegroundColor Red
            }
        } else {
            Write-Host "`nℹ️  After you have the backup file, run:" -ForegroundColor Cyan
            Write-Host "Get-Content your-backup.sql | docker-compose exec -T postgres psql -U fantacalcio_user -d fantacalcio_db" -ForegroundColor White
        }
    }
    
    "2" {
        Write-Host "`n🔗 Option 2: Direct Connection to Xeon" -ForegroundColor Yellow
        Write-Host "=" * 60
        
        Write-Host "`nTo connect your local app to the Xeon database:" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "1. Edit .env file and change DATABASE_URL:" -ForegroundColor White
        Write-Host "   DATABASE_URL=postgresql://user:password@xeon-server-ip:5432/fantacalcio_db" -ForegroundColor Gray
        Write-Host ""
        Write-Host "2. Ensure Xeon PostgreSQL allows remote connections:" -ForegroundColor White
        Write-Host "   - Edit postgresql.conf: listen_addresses = '*'" -ForegroundColor Gray
        Write-Host "   - Edit pg_hba.conf: Add line for your IP" -ForegroundColor Gray
        Write-Host "   - Restart PostgreSQL: systemctl restart postgresql" -ForegroundColor Gray
        Write-Host ""
        Write-Host "3. Ensure firewall allows PostgreSQL:" -ForegroundColor White
        Write-Host "   sudo ufw allow 5432/tcp" -ForegroundColor Gray
        Write-Host ""
        Write-Host "⚠️  Not recommended for production - use for testing only!" -ForegroundColor Red
    }
    
    "3" {
        Write-Host "`n🆕 Option 3: Fresh Database with Schema Only" -ForegroundColor Cyan
        Write-Host "=" * 60
        
        Write-Host "`nInitializing fresh database with schema..." -ForegroundColor Yellow
        docker-compose exec app python init_db.py --create-admin
        
        Write-Host "`n✅ Fresh database initialized!" -ForegroundColor Green
        Write-Host "You now have an empty database with all tables created." -ForegroundColor White
    }
    
    default {
        Write-Host "`n❌ Invalid option" -ForegroundColor Red
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Migration Helper Complete" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan
