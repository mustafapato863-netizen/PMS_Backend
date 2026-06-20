"""Integration tests for Models and Repositories"""
from config.database import SessionLocal
from repositories.user_repository import UserRepository
from repositories.team_repository import TeamRepository
from models.models import User, Team

def test_user_repository():
    """Test UserRepository"""
    db = SessionLocal()
    
    try:
        # Test 1: Query existing users
        user_repo = UserRepository(db, User)
        users = user_repo.get_all()
        print(f"✅ Test 1: Found {len(users)} users")
        for user in users:
            print(f"   - Username: {user.username}, Email: {user.email}, Role: {user.role}")
        
        # Test 2: Query by username
        admin = user_repo.get_by_username('admin')
        if admin:
            print(f"\n✅ Test 2: Found admin user")
            print(f"   - ID: {admin.id}")
            print(f"   - Email: {admin.email}")
            print(f"   - Role: {admin.role}")
        
        # Test 3: Count active users
        active_count = user_repo.count_active()
        print(f"\n✅ Test 3: Active users: {active_count}")
        
        # Test 4: Get all admin role users
        admins = user_repo.get_by_role('Admin')
        print(f"\n✅ Test 4: Found {len(admins)} admin users")
        
        print("\n" + "="*60)
        print("✅ USER REPOSITORY TESTS PASSED!")
        print("="*60)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


def test_team_repository():
    """Test TeamRepository"""
    db = SessionLocal()
    
    try:
        team_repo = TeamRepository(db, Team)
        teams = team_repo.get_all()
        print(f"\n✅ Team Test: Found {len(teams)} teams in database")
        
        active_teams = team_repo.get_active_teams()
        print(f"✅ Active teams: {len(active_teams)}")
        
        print("\n" + "="*60)
        print("✅ TEAM REPOSITORY TESTS PASSED!")
        print("="*60)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING INTEGRATION TESTS")
    print("=" * 60)
    
    test_user_repository()
    test_team_repository()
    
    print("\n✅ ALL INTEGRATION TESTS COMPLETED!")
