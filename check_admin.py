"""
Script to check and set admin status for users
"""
from app import app, db
from models import User

def check_users():
    with app.app_context():
        users = User.query.all()
        print(f"\n{'='*60}")
        print(f"Total users in database: {len(users)}")
        print(f"{'='*60}\n")
        
        for user in users:
            print(f"ID: {user.id}")
            print(f"Username: {user.username}")
            print(f"Email: {user.email}")
            print(f"Is Admin: {user.is_admin}")
            print(f"Is Active: {user.is_active}")
            print(f"Created At: {user.created_at}")
            print("-" * 60)

def make_admin(email):
    """Make a user admin by email"""
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if user:
            user.is_admin = True
            db.session.commit()
            print(f"✅ User {email} is now an admin!")
            return True
        else:
            print(f"❌ User with email {email} not found!")
            return False

if __name__ == "__main__":
    print("\n" + "="*60)
    print("ADMIN USER CHECKER")
    print("="*60)
    
    # First, show all users
    check_users()
    
    # Ask if user wants to make someone admin
    print("\nDo you want to make a user admin?")
    print("1. Yes, enter email")
    print("2. No, just checking")
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "1":
        email = input("Enter user email: ").strip()
        make_admin(email)
        print("\nUpdated user list:")
        check_users()
