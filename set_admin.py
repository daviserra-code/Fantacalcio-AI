"""
Simple script to set a user as admin
"""
import os
import sys

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file BEFORE importing app
import config  # This loads the .env file

from app import app, db
from models import User

def list_users():
    """List all users"""
    with app.app_context():
        users = User.query.all()
        print(f"\n{'='*80}")
        print(f"USERS IN DATABASE ({len(users)} total)")
        print(f"{'='*80}\n")
        
        if not users:
            print("❌ No users found in database!")
            return []
        
        for i, user in enumerate(users, 1):
            print(f"{i}. ID: {user.id}")
            print(f"   Username: {user.username}")
            print(f"   Email: {user.email}")
            print(f"   Is Admin: {'✅ YES' if user.is_admin else '❌ NO'}")
            print(f"   Created: {user.created_at}")
            print("-" * 80)
        
        return users

def make_all_admins():
    """Make ALL users admins (for testing)"""
    with app.app_context():
        users = User.query.all()
        count = 0
        for user in users:
            if not user.is_admin:
                user.is_admin = True
                count += 1
        
        db.session.commit()
        print(f"\n✅ Made {count} user(s) admin!")
        return count

if __name__ == "__main__":
    print("\n" + "="*80)
    print("ADMIN USER MANAGER")
    print("="*80)
    
    # List all users
    users = list_users()
    
    if users:
        print("\n" + "="*80)
        print("MAKING ALL USERS ADMIN...")
        print("="*80)
        count = make_all_admins()
        
        if count > 0:
            print("\n" + "="*80)
            print("UPDATED USER LIST:")
            print("="*80)
            list_users()
