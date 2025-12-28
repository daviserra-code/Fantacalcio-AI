# Phase 2: Implementation Plan with Apify Integration

## 🎯 Execution Order: Option 1 → 2 → 3

### Test-Driven Approach
✅ Implement feature  
✅ Test thoroughly  
✅ Git checkpoint  
✅ Move to next feature

---

## 📋 Your Apify Assets (Documented)

### **Apify Actors Available**:
1. **`TransfermarktScraperDS`** - Custom actor for:
   - Player transfers (arrivals/departures)
   - Player profiles and stats
   - Market values
   - Position data

2. **Configuration**:
   - Rate limits: 60 req/min, 3 concurrent runs
   - 20 Serie A teams configured with URLs
   - Position mapping (Transfermarkt → P/D/C/A)

3. **Environment Variables**:
   - `APIFY_API_TOKEN` - Your API token
   - `USE_APIFY_TRANSFERMARKT=1` - Enable/disable

### **Integration Benefits for Phase 2**:
- ✅ **Real-time player data** for filtering
- ✅ **Live transfer updates** for comparison tool
- ✅ **Current quotas/prices** from Fantacalcio sources
- ✅ **Market value tracking** for analytics

---

## 🚀 PHASE 2-A: Enhanced Filtering & Search

### **Timeline**: 2 days
**Start**: After this planning session  
**Testing**: After implementation  
**Checkpoint**: Git commit before Priority 3

### **Features to Implement**:

#### 1. Multi-Criteria Filter Backend (Day 1, Morning)

**File**: `routes.py`
```python
@app.route('/api/players/search/advanced', methods=['POST'])
@login_required
def search_players_advanced():
    """Advanced player search with multiple criteria"""
    from fantacalcio_assistant import FantacalcioAssistant
    
    filters = request.get_json()
    
    # Extract filters
    roles = filters.get('roles', [])  # ['D', 'C']
    teams = filters.get('teams', [])  # ['Juventus', 'Inter']
    price_min = filters.get('price_min', 0)
    price_max = filters.get('price_max', 999)
    fantamedia_min = filters.get('fantamedia_min', 0)
    under21 = filters.get('under21', False)
    appearances_min = filters.get('appearances_min', 0)
    search_text = filters.get('search', '')
    
    # Load roster
    assistant = FantacalcioAssistant()
    assistant._ensure_data_loaded()
    players = assistant.roster
    
    # Apply filters
    filtered = []
    for player in players:
        # Role filter
        if roles and player.get('role') not in roles:
            continue
        
        # Team filter
        if teams and player.get('team') not in teams:
            continue
        
        # Price filter
        price = player.get('price', 0) or 0
        if price < price_min or price > price_max:
            continue
        
        # Fantamedia filter
        fm = player.get('fantamedia', 0) or 0
        if fm < fantamedia_min:
            continue
        
        # Under 21 filter
        if under21:
            birth_year = player.get('birth_year')
            if not birth_year or (2025 - birth_year) > 21:
                continue
        
        # Appearances filter
        appearances = player.get('appearances', 0) or 0
        if appearances < appearances_min:
            continue
        
        # Text search (fuzzy)
        if search_text:
            name = player.get('name', '').lower()
            if search_text.lower() not in name:
                continue
        
        # Calculate efficiency
        player['efficiency'] = round(fm / price * 100, 2) if price > 0 else 0
        
        filtered.append(player)
    
    # Sort by fantamedia descending
    filtered.sort(key=lambda x: x.get('fantamedia', 0), reverse=True)
    
    return jsonify({
        'count': len(filtered),
        'total_available': len(players),
        'players': filtered[:100],  # Limit results
        'filters_applied': filters
    })
```

**File**: `routes.py` (Quick Filters)
```python
@app.route('/api/players/quick-filters/<filter_name>')
@login_required
def quick_filter(filter_name):
    """Predefined quick filters"""
    
    QUICK_FILTERS = {
        'best_value_defenders': {
            'roles': ['D'],
            'price_max': 30,
            'fantamedia_min': 20,
            'sort': 'efficiency'
        },
        'under21_forwards': {
            'roles': ['A'],
            'under21': True,
            'appearances_min': 5
        },
        'budget_midfielders': {
            'roles': ['C'],
            'price_max': 15,
            'fantamedia_min': 15
        },
        'premium_players': {
            'price_min': 40,
            'fantamedia_min': 25
        }
    }
    
    filter_config = QUICK_FILTERS.get(filter_name)
    if not filter_config:
        return jsonify({'error': 'Filter not found'}), 404
    
    # Use advanced search with predefined config
    return search_players_advanced()
```

#### 2. Frontend UI (Day 1, Afternoon)

**File**: `templates/players_search.html` (New template)
```html
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Advanced Player Search - FantaCalcio AI</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <div class="container mt-4">
        <h2><i class="fas fa-search me-2"></i>Advanced Player Search</h2>
        
        <!-- Quick Filters -->
        <div class="mb-4">
            <h5>Quick Filters:</h5>
            <button class="btn btn-sm btn-outline-primary" onclick="applyQuickFilter('best_value_defenders')">
                <i class="fas fa-shield-alt"></i> Best Value Defenders
            </button>
            <button class="btn btn-sm btn-outline-success" onclick="applyQuickFilter('under21_forwards')">
                <i class="fas fa-running"></i> Under 21 Forwards
            </button>
            <button class="btn btn-sm btn-outline-info" onclick="applyQuickFilter('budget_midfielders')">
                <i class="fas fa-coins"></i> Budget Midfielders
            </button>
            <button class="btn btn-sm btn-outline-warning" onclick="applyQuickFilter('premium_players')">
                <i class="fas fa-star"></i> Premium Players
            </button>
        </div>
        
        <!-- Advanced Filters -->
        <div class="card mb-4">
            <div class="card-header">
                <h5 class="mb-0">
                    <i class="fas fa-filter me-2"></i>Advanced Filters
                </h5>
            </div>
            <div class="card-body">
                <!-- Search by name -->
                <div class="mb-3">
                    <label class="form-label">Search by Name:</label>
                    <input type="text" id="searchText" class="form-control" placeholder="Enter player name...">
                </div>
                
                <!-- Role selection -->
                <div class="mb-3">
                    <label class="form-label">Role:</label>
                    <div class="btn-group" role="group">
                        <input type="checkbox" class="btn-check" id="role_all" checked>
                        <label class="btn btn-outline-secondary" for="role_all">All</label>
                        
                        <input type="checkbox" class="btn-check role-filter" id="role_P" value="P">
                        <label class="btn btn-outline-primary" for="role_P">P</label>
                        
                        <input type="checkbox" class="btn-check role-filter" id="role_D" value="D">
                        <label class="btn btn-outline-success" for="role_D">D</label>
                        
                        <input type="checkbox" class="btn-check role-filter" id="role_C" value="C">
                        <label class="btn btn-outline-info" for="role_C">C</label>
                        
                        <input type="checkbox" class="btn-check role-filter" id="role_A" value="A">
                        <label class="btn btn-outline-danger" for="role_A">A</label>
                    </div>
                </div>
                
                <!-- Team selection -->
                <div class="mb-3">
                    <label class="form-label">Teams:</label>
                    <select id="teamSelect" class="form-select" multiple>
                        <option value="Juventus">Juventus</option>
                        <option value="Inter">Inter</option>
                        <option value="Milan">Milan</option>
                        <option value="Napoli">Napoli</option>
                        <option value="Roma">Roma</option>
                        <option value="Lazio">Lazio</option>
                        <option value="Atalanta">Atalanta</option>
                        <!-- Add all Serie A teams -->
                    </select>
                    <small class="text-muted">Hold Ctrl to select multiple teams</small>
                </div>
                
                <!-- Price range -->
                <div class="mb-3">
                    <label class="form-label">Price Range: <span id="priceRangeLabel">€10 - €50</span></label>
                    <div class="row">
                        <div class="col-6">
                            <input type="range" class="form-range" id="priceMin" min="0" max="100" value="10">
                        </div>
                        <div class="col-6">
                            <input type="range" class="form-range" id="priceMax" min="0" max="100" value="50">
                        </div>
                    </div>
                </div>
                
                <!-- Fantamedia range -->
                <div class="mb-3">
                    <label class="form-label">Min Fantamedia: <span id="fantamediaLabel">20</span></label>
                    <input type="range" class="form-range" id="fantamediaMin" min="0" max="35" value="20">
                </div>
                
                <!-- Checkboxes -->
                <div class="mb-3">
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="under21Check">
                        <label class="form-check-label" for="under21Check">
                            Only Under 21 players
                        </label>
                    </div>
                </div>
                
                <!-- Action buttons -->
                <div class="d-flex justify-content-between">
                    <button class="btn btn-primary" onclick="searchPlayers()">
                        <i class="fas fa-search me-2"></i>Search
                    </button>
                    <button class="btn btn-outline-secondary" onclick="resetFilters()">
                        <i class="fas fa-redo me-2"></i>Reset
                    </button>
                </div>
            </div>
        </div>
        
        <!-- Results -->
        <div id="results" class="card">
            <div class="card-header">
                <h5 class="mb-0">
                    <i class="fas fa-list me-2"></i>Results <span id="resultCount" class="badge bg-primary">0</span>
                </h5>
            </div>
            <div class="card-body">
                <div id="playersList"></div>
            </div>
        </div>
    </div>
    
    <script>
        // Update range labels
        document.getElementById('priceMin').addEventListener('input', updatePriceLabel);
        document.getElementById('priceMax').addEventListener('input', updatePriceLabel);
        document.getElementById('fantamediaMin').addEventListener('input', updateFantamediaLabel);
        
        function updatePriceLabel() {
            const min = document.getElementById('priceMin').value;
            const max = document.getElementById('priceMax').value;
            document.getElementById('priceRangeLabel').textContent = `€${min} - €${max}`;
        }
        
        function updateFantamediaLabel() {
            const val = document.getElementById('fantamediaMin').value;
            document.getElementById('fantamediaLabel').textContent = val;
        }
        
        function searchPlayers() {
            // Gather filters
            const filters = {
                search: document.getElementById('searchText').value,
                roles: Array.from(document.querySelectorAll('.role-filter:checked')).map(cb => cb.value),
                teams: Array.from(document.getElementById('teamSelect').selectedOptions).map(opt => opt.value),
                price_min: parseInt(document.getElementById('priceMin').value),
                price_max: parseInt(document.getElementById('priceMax').value),
                fantamedia_min: parseInt(document.getElementById('fantamediaMin').value),
                under21: document.getElementById('under21Check').checked
            };
            
            // Make API call
            fetch('/api/players/search/advanced', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(filters)
            })
            .then(res => res.json())
            .then(data => displayResults(data))
            .catch(err => console.error('Search error:', err));
        }
        
        function displayResults(data) {
            const list = document.getElementById('playersList');
            document.getElementById('resultCount').textContent = data.count;
            
            if (data.count === 0) {
                list.innerHTML = '<p class="text-muted">No players found matching your criteria.</p>';
                return;
            }
            
            let html = '<div class="table-responsive"><table class="table table-hover"><thead><tr>';
            html += '<th>Name</th><th>Role</th><th>Team</th><th>Price</th><th>Fantamedia</th><th>Efficiency</th>';
            html += '</tr></thead><tbody>';
            
            data.players.forEach(player => {
                html += `<tr>
                    <td><strong>${player.name}</strong></td>
                    <td><span class="badge bg-secondary">${player.role}</span></td>
                    <td>${player.team}</td>
                    <td>€${player.price}</td>
                    <td>${player.fantamedia}</td>
                    <td>${player.efficiency}</td>
                </tr>`;
            });
            
            html += '</tbody></table></div>';
            list.innerHTML = html;
        }
        
        function resetFilters() {
            document.getElementById('searchText').value = '';
            document.querySelectorAll('.role-filter').forEach(cb => cb.checked = false);
            document.getElementById('teamSelect').selectedIndex = -1;
            document.getElementById('priceMin').value = 10;
            document.getElementById('priceMax').value = 50;
            document.getElementById('fantamediaMin').value = 20;
            document.getElementById('under21Check').checked = false;
            updatePriceLabel();
            updateFantamediaLabel();
        }
        
        function applyQuickFilter(filterName) {
            fetch(`/api/players/quick-filters/${filterName}`)
                .then(res => res.json())
                .then(data => displayResults(data))
                .catch(err => console.error('Quick filter error:', err));
        }
    </script>
</body>
</html>
```

#### 3. Route Registration (Day 1)

**File**: `routes.py`
```python
@app.route('/players/search')
@login_required
def players_search_page():
    """Player search page"""
    return render_template('players_search.html', user=current_user)
```

#### 4. Testing (Day 2, Morning)

**Create**: `test_phase2a_filtering.py`
```python
#!/usr/bin/env python3
"""
Test suite for Phase 2A: Enhanced Filtering
"""

import requests
import json

BASE_URL = "http://localhost:5000"

def test_advanced_search():
    """Test advanced search API"""
    print("\n🧪 Testing Advanced Search...")
    
    filters = {
        "roles": ["D"],
        "price_min": 10,
        "price_max": 30,
        "fantamedia_min": 20
    }
    
    response = requests.post(
        f"{BASE_URL}/api/players/search/advanced",
        json=filters,
        # Add auth if needed
    )
    
    assert response.status_code == 200, f"Failed: {response.status_code}"
    data = response.json()
    
    assert 'count' in data
    assert 'players' in data
    
    # Validate filter was applied
    for player in data['players']:
        assert player['role'] == 'D'
        assert player['price'] >= 10 and player['price'] <= 30
        assert player['fantamedia'] >= 20
    
    print(f"✅ Advanced Search: {data['count']} players found")
    return True

def test_quick_filters():
    """Test quick filter endpoints"""
    print("\n🧪 Testing Quick Filters...")
    
    filters = [
        'best_value_defenders',
        'under21_forwards',
        'budget_midfielders',
        'premium_players'
    ]
    
    for filter_name in filters:
        response = requests.get(f"{BASE_URL}/api/players/quick-filters/{filter_name}")
        assert response.status_code == 200
        data = response.json()
        print(f"  ✅ {filter_name}: {data['count']} players")
    
    return True

def test_ui_page():
    """Test search page loads"""
    print("\n🧪 Testing UI Page...")
    
    response = requests.get(f"{BASE_URL}/players/search")
    assert response.status_code == 200
    assert b"Advanced Player Search" in response.content
    
    print("✅ Search page loads successfully")
    return True

if __name__ == "__main__":
    print("=" * 50)
    print("PHASE 2A: ENHANCED FILTERING - TEST SUITE")
    print("=" * 50)
    
    tests = [
        test_advanced_search,
        test_quick_filters,
        test_ui_page
    ]
    
    passed = 0
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed: {e}")
    
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{len(tests)} tests passed")
    print(f"{'='*50}")
```

---

## ✅ Checkpoint 1: After Priority 4

```bash
# Test
python test_phase2a_filtering.py

# Git commit
git add .
git commit -m "Phase 2A: Enhanced filtering with multi-criteria search and quick filters"
```

---

## 🚀 PHASE 2-B: Player Comparison Tool

*(Details in next message after Priority 4 is complete)*

---

## 🚀 PHASE 2-C: Enhanced League System

*(Details in next message after Priority 3 is complete)*

---

## 📝 Current Session Plan

1. ✅ Review this plan
2. ✅ Create safety checkpoint (git commit)
3. ✅ Start Priority 4 implementation
4. ✅ Test Priority 4
5. ✅ Git checkpoint
6. → Move to Priority 3

**Ready to start Priority 4?**
