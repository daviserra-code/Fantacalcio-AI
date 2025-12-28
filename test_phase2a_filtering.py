"""
Test Suite for Phase 2A - Enhanced Player Filtering & Search
Tests advanced search, quick filters, and UI page endpoints
"""

import sys
import json
from app import app, db
from models import User
from flask_login import login_user

def create_test_user():
    """Create or get test user"""
    with app.app_context():
        test_user = User.query.filter_by(email='test@test.com').first()
        if not test_user:
            print("⚠️  Creating test user...")
            test_user = User(
                username='testuser',
                email='test@test.com',
                first_name='Test',
                last_name='User',
                is_admin=True
            )
            test_user.set_password('testpass123')
            db.session.add(test_user)
            db.session.commit()
            print("✅ Test user created")
        return test_user

def test_advanced_search():
    """Test the advanced search API with various filter combinations"""
    print("\n=== Testing Advanced Search API ===")
    
    user = create_test_user()
    
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        
        # Test 1: Search with role filter only
        print("\n📝 Test 1: Search for defenders...")
        response = client.post('/api/players/search/advanced',
            json={'roles': ['D']},
            content_type='application/json'
        )
        
        if response.status_code == 200:
            data = response.get_json()
            if data.get('success'):
                print(f"✅ Found {data['count']} defenders")
                if data['count'] > 0:
                    print(f"   Sample: {data['players'][0]['name']} - {data['players'][0]['team']}")
            else:
                print(f"❌ Error: {data.get('error')}")
                return False
        else:
            print(f"❌ HTTP {response.status_code}")
            return False
        
        # Test 2: Search with price range
        print("\n📝 Test 2: Search for budget players (€1-10)...")
        response = client.post('/api/players/search/advanced',
            json={'price_min': 1, 'price_max': 10},
            content_type='application/json'
        )
        
        if response.status_code == 200:
            data = response.get_json()
            if data.get('success'):
                print(f"✅ Found {data['count']} budget players")
                if data['count'] > 0:
                    sample = data['players'][0]
                    print(f"   Sample: {sample['name']} - €{sample['price']}")
            else:
                print(f"❌ Error: {data.get('error')}")
                return False
        else:
            print(f"❌ HTTP {response.status_code}")
            return False
        
        # Test 3: Search with fantamedia minimum
        print("\n📝 Test 3: Search for high performers (Fantamedia ≥ 20)...")
        response = client.post('/api/players/search/advanced',
            json={'fantamedia_min': 20},
            content_type='application/json'
        )
        
        if response.status_code == 200:
            data = response.get_json()
            if data.get('success'):
                print(f"✅ Found {data['count']} high performers")
                if data['count'] > 0:
                    sample = data['players'][0]
                    print(f"   Sample: {sample['name']} - FM: {sample['fantamedia']}, Eff: {sample['efficiency']}")
            else:
                print(f"❌ Error: {data.get('error')}")
                return False
        else:
            print(f"❌ HTTP {response.status_code}")
            return False
        
        # Test 4: Combined filters (role + price + fantamedia)
        print("\n📝 Test 4: Combined filters (Forwards, €10-30, FM≥15)...")
        response = client.post('/api/players/search/advanced',
            json={
                'roles': ['A'],
                'price_min': 10,
                'price_max': 30,
                'fantamedia_min': 15
            },
            content_type='application/json'
        )
        
        if response.status_code == 200:
            data = response.get_json()
            if data.get('success'):
                print(f"✅ Found {data['count']} matching forwards")
                if data['count'] > 0:
                    sample = data['players'][0]
                    print(f"   Sample: {sample['name']} - €{sample['price']}, FM: {sample['fantamedia']}")
                print(f"   Filters applied: {data.get('filters_applied', {})}")
            else:
                print(f"❌ Error: {data.get('error')}")
                return False
        else:
            print(f"❌ HTTP {response.status_code}")
            return False
        
        # Test 5: Under 21 filter
        print("\n📝 Test 5: Under 21 players...")
        response = client.post('/api/players/search/advanced',
            json={'under21': True},
            content_type='application/json'
        )
        
        if response.status_code == 200:
            data = response.get_json()
            if data.get('success'):
                print(f"✅ Found {data['count']} under 21 players")
            else:
                print(f"❌ Error: {data.get('error')}")
                return False
        else:
            print(f"❌ HTTP {response.status_code}")
            return False
        
        # Test 6: Team filter
        print("\n📝 Test 6: Players from specific team (Inter)...")
        response = client.post('/api/players/search/advanced',
            json={'teams': ['Inter']},
            content_type='application/json'
        )
        
        if response.status_code == 200:
            data = response.get_json()
            if data.get('success'):
                print(f"✅ Found {data['count']} Inter players")
                if data['count'] > 0:
                    print(f"   Sample: {data['players'][0]['name']}")
            else:
                print(f"❌ Error: {data.get('error')}")
                return False
        else:
            print(f"❌ HTTP {response.status_code}")
            return False
        
        print("\n✅ All advanced search tests passed!")
        return True

def test_quick_filters():
    """Test all predefined quick filter endpoints"""
    print("\n=== Testing Quick Filters ===")
    
    user = create_test_user()
    
    quick_filters = [
        'best_value_defenders',
        'under21_forwards',
        'budget_midfielders',
        'premium_players',
        'top_goalkeepers',
        'bargain_hunters'
    ]
    
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        
        for filter_name in quick_filters:
            print(f"\n📝 Testing '{filter_name}'...")
            response = client.get(f'/api/players/quick-filters/{filter_name}')
            
            if response.status_code == 200:
                data = response.get_json()
                if data.get('success'):
                    print(f"   ✅ Found {data['count']} players")
                    if data['count'] > 0:
                        sample = data['players'][0]
                        print(f"   Sample: {sample['name']} - {sample['role']} - €{sample['price']}")
                else:
                    print(f"   ❌ Error: {data.get('error')}")
                    return False
            else:
                print(f"   ❌ HTTP {response.status_code}")
                return False
        
        # Test invalid filter
        print(f"\n📝 Testing invalid filter name...")
        response = client.get(f'/api/players/quick-filters/invalid_filter')
        if response.status_code == 404:
            data = response.get_json()
            print(f"   ✅ Correctly returned 404 with {len(data.get('available_filters', []))} available filters")
        else:
            print(f"   ❌ Expected 404, got {response.status_code}")
            return False
        
        print("\n✅ All quick filter tests passed!")
        return True

def test_ui_page():
    """Test that the search page loads correctly"""
    print("\n=== Testing Search Page UI ===")
    
    user = create_test_user()
    
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        
        print("\n📝 Loading /players/search page...")
        response = client.get('/players/search')
        
        if response.status_code == 200:
            html = response.data.decode('utf-8')
            
            # Check for key elements
            checks = [
                ('Quick Filters section', 'Quick Filters' in html),
                ('Advanced Filters section', 'Advanced Filters' in html),
                ('Role checkboxes', 'role_P' in html and 'role_D' in html),
                ('Team select', 'teamSelect' in html),
                ('Price sliders', 'priceMin' in html and 'priceMax' in html),
                ('Search button', 'searchPlayers()' in html),
                ('Quick filter buttons', 'applyQuickFilter' in html),
                ('Bootstrap CSS', 'bootstrap' in html),
                ('Font Awesome icons', 'font-awesome' in html or 'fontawesome' in html)
            ]
            
            all_passed = True
            for check_name, check_result in checks:
                status = "✅" if check_result else "❌"
                print(f"   {status} {check_name}")
                if not check_result:
                    all_passed = False
            
            if all_passed:
                print("\n✅ Search page UI test passed!")
                return True
            else:
                print("\n❌ Some UI elements missing")
                return False
        else:
            print(f"❌ HTTP {response.status_code}")
            return False

def run_all_tests():
    """Run complete test suite"""
    print("\n" + "="*60)
    print("PHASE 2A - ENHANCED FILTERING TEST SUITE")
    print("="*60)
    
    results = {
        'Advanced Search': test_advanced_search(),
        'Quick Filters': test_quick_filters(),
        'UI Page': test_ui_page()
    }
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Phase 2A implementation successful.")
        print("="*60)
        return 0
    else:
        print("⚠️  SOME TESTS FAILED. Please review the output above.")
        print("="*60)
        return 1

if __name__ == '__main__':
    exit_code = run_all_tests()
    sys.exit(exit_code)
