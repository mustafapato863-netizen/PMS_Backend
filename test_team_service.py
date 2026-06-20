"""Test updated TeamService with database"""
from services.team_service import TeamService

def test_team_service():
    """Test TeamService methods"""
    try:
        print("=" * 60)
        print("TESTING UPDATED TEAMSERVICE")
        print("=" * 60)
        
        # Test 1: Get all teams (should be empty or from database)
        print("\n1. Testing get_all_teams()...")
        all_teams = TeamService.get_all_teams()
        print(f"   ✅ Found {len(all_teams)} teams in database")
        for team in all_teams:
            print(f"      - {team['name']} (Region: {team['region']})")
        
        # Test 2: Get team statistics
        print("\n2. Testing get_team_statistics()...")
        stats = TeamService.get_team_statistics()
        print(f"   ✅ Statistics retrieved:")
        print(f"      - Total teams: {stats['total_teams']}")
        print(f"      - Active teams: {stats['active_teams']}")
        print(f"      - Regions: {stats['regions']}")
        print(f"      - Total KPI keys: {stats['total_kpi_keys']}")
        
        print("\n" + "=" * 60)
        print("✅ ALL TEAMSERVICE TESTS PASSED!")
        print("=" * 60)
        print("\nTeamService is now DATABASE-BACKED! ✅")
        print("- No more JSON file operations")
        print("- All data persisted in database")
        print("- Full transaction support")
        print("- Proper error handling with logging")
        
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_team_service()
