# -*- coding: utf-8 -*-
"""
Test Suite for Phase 2B: Player Comparison Tool
Tests comparison API, percentile calculations, UI integration, and search functionality
"""

import sys
import os
import pytest
from flask import session
from flask_login import login_user

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import User


class TestPlayerComparisonAPI:
    """Test suite for /api/players/compare endpoint"""
    
    @pytest.fixture
    def client(self):
        """Create a test client with authentication"""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['LOGIN_DISABLED'] = True  # Disable login requirement for tests
        with app.test_client() as client:
            yield client
    
    def test_compare_two_players(self, client):
        """Test comparison with 2 valid players"""
        response = client.post('/api/players/compare',
                              json={'players': ['Lautaro Martinez', 'Victor Osimhen']},
                              content_type='application/json')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['count'] == 2
        assert len(data['players']) == 2
        
        # Check structure of each player
        for player in data['players']:
            assert 'name' in player
            assert 'role' in player
            assert 'price' in player
            assert 'fantamedia' in player
            assert 'efficiency' in player
            assert 'percentiles' in player
            assert 'price' in player['percentiles']
            assert 'fantamedia' in player['percentiles']
            assert 'appearances' in player['percentiles']
        
        # Check averages
        assert 'averages' in data
        assert 'price' in data['averages']
        assert 'fantamedia' in data['averages']
        assert 'efficiency' in data['averages']
    
    def test_compare_four_players(self, client):
        """Test comparison with 4 players (maximum)"""
        response = client.post('/api/players/compare',
                              json={'players': ['Lautaro Martinez', 'Victor Osimhen', 
                                              'Duvan Zapata', 'Andrea Belotti']},
                              content_type='application/json')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['count'] == 4
        assert len(data['players']) == 4
    
    def test_compare_minimum_players_error(self, client):
        """Test error when providing only 1 player"""
        response = client.post('/api/players/compare',
                              json={'players': ['Lautaro Martinez']},
                              content_type='application/json')
        
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'minimo 2' in data['error'].lower()
    
    def test_compare_maximum_players_error(self, client):
        """Test error when providing more than 4 players"""
        response = client.post('/api/players/compare',
                              json={'players': ['Player1', 'Player2', 'Player3', 
                                              'Player4', 'Player5']},
                              content_type='application/json')
        
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'massimo 4' in data['error'].lower()
    
    def test_compare_invalid_players(self, client):
        """Test comparison with non-existent players"""
        response = client.post('/api/players/compare',
                              json={'players': ['ZZZ_NonExistent1', 'ZZZ_NonExistent2']},
                              content_type='application/json')
        
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False
        assert 'non trovati' in data['error'].lower()
    
    def test_compare_mixed_valid_invalid(self, client):
        """Test comparison with mix of valid and invalid players"""
        response = client.post('/api/players/compare',
                              json={'players': ['Lautaro Martinez', 'ZZZ_NonExistent']},
                              content_type='application/json')
        
        # Should return partial results
        data = response.get_json()
        if response.status_code == 200:
            # If endpoint allows partial matches
            assert 'not_found' in data
            assert 'ZZZ_NonExistent' in data['not_found']
        else:
            # If endpoint requires all players to exist
            assert response.status_code == 404
    
    def test_compare_missing_json_body(self, client):
        """Test error when JSON body is missing"""
        response = client.post('/api/players/compare')
        
        assert response.status_code in [400, 415]  # Bad Request or Unsupported Media Type
    
    def test_compare_empty_players_list(self, client):
        """Test error with empty players list"""
        response = client.post('/api/players/compare',
                              json={'players': []},
                              content_type='application/json')
        
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False


class TestPercentileCalculations:
    """Test suite for percentile calculation logic"""
    
    @pytest.fixture
    def client(self):
        """Create a test client with authentication"""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['LOGIN_DISABLED'] = True
        with app.test_client() as client:
            yield client
    
    def test_percentiles_range(self, client):
        """Test that percentiles are between 0 and 100"""
        response = client.post('/api/players/compare',
                              json={'players': ['Lautaro Martinez', 'Victor Osimhen']},
                              content_type='application/json')
        
        assert response.status_code == 200
        data = response.get_json()
        
        for player in data['players']:
            for key, value in player['percentiles'].items():
                assert 0 <= value <= 100, f"{key} percentile out of range: {value}"
    
    def test_efficiency_calculation(self, client):
        """Test efficiency metric calculation"""
        response = client.post('/api/players/compare',
                              json={'players': ['Lautaro Martinez', 'Victor Osimhen']},
                              content_type='application/json')
        
        assert response.status_code == 200
        data = response.get_json()
        
        for player in data['players']:
            efficiency = player['efficiency']
            price = player['price']
            fantamedia = player['fantamedia']
            
            # Efficiency should be (fantamedia / price) * 100 (rounded to 2 decimals)
            if price and price > 0:
                expected_efficiency = round((fantamedia / price) * 100, 2)
                assert abs(efficiency - expected_efficiency) < 0.1, \
                    f"Efficiency mismatch for {player['name']}: {efficiency} vs {expected_efficiency}"
    
    def test_averages_calculation(self, client):
        """Test that averages are correctly calculated"""
        response = client.post('/api/players/compare',
                              json={'players': ['Lautaro Martinez', 'Victor Osimhen']},
                              content_type='application/json')
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Calculate manual averages
        total_price = sum(p['price'] for p in data['players'] if p['price'])
        total_fm = sum(p['fantamedia'] for p in data['players'] if p['fantamedia'])
        count = data['count']
        
        avg_price = round(total_price / count, 2)
        avg_fm = round(total_fm / count, 2)
        
        # Compare with API averages
        assert abs(data['averages']['price'] - avg_price) < 0.1
        assert abs(data['averages']['fantamedia'] - avg_fm) < 0.1


class TestComparisonPageUI:
    """Test suite for /players/compare page"""
    
    @pytest.fixture
    def client(self):
        """Create a test client with authentication"""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['LOGIN_DISABLED'] = True
        with app.test_client() as client:
            yield client
    
    def test_comparison_page_loads(self, client):
        """Test that comparison page loads successfully"""
        response = client.get('/players/compare')
        
        assert response.status_code == 200
        assert b'Confronto Giocatori' in response.data
        assert b'radarChart' in response.data  # Canvas for Chart.js
    
    def test_comparison_page_italian_text(self, client):
        """Test that page uses Italian language"""
        response = client.get('/players/compare')
        
        assert response.status_code == 200
        # Check Italian labels
        assert b'Seleziona Giocatori' in response.data
        assert b'Confronta' in response.data
        assert b'Statistiche' in response.data or b'statistiche' in response.data
    
    def test_comparison_page_dark_mode_support(self, client):
        """Test that dark mode CSS variables are present"""
        response = client.get('/players/compare')
        
        assert response.status_code == 200
        assert b'data-theme' in response.data
        assert b'--bg-primary' in response.data
        assert b'--text-primary' in response.data
    
    def test_comparison_page_with_query_params(self, client):
        """Test page loads with initial player query params"""
        response = client.get('/players/compare?players=Lautaro Martinez&players=Victor Osimhen')
        
        assert response.status_code == 200
        # Page should load and JavaScript will fetch comparison data
    
    def test_comparison_page_unauthenticated(self, client):
        """Test that comparison page requires authentication"""
        # Create client without session
        with app.test_client() as unauth_client:
            response = unauth_client.get('/players/compare')
            # Should redirect to login or return 401/403
            assert response.status_code in [302, 401, 403]


class TestSearchIntegration:
    """Test suite for search page integration with comparison"""
    
    @pytest.fixture
    def client(self):
        """Create a test client with authentication"""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['LOGIN_DISABLED'] = True
        with app.test_client() as client:
            yield client
    
    def test_search_page_has_comparison_features(self, client):
        """Test that search page includes comparison checkboxes"""
        response = client.get('/players/search')
        
        assert response.status_code == 200
        # Check for comparison button and JavaScript functions
        assert b'compareBtn' in response.data or b'Confronta' in response.data
        assert b'updateCompareButton' in response.data
        assert b'compareSelected' in response.data
    
    def test_search_page_comparison_link(self, client):
        """Test that search page has link to comparison page"""
        response = client.get('/players/search')
        
        assert response.status_code == 200
        assert b'/players/compare' in response.data


class TestEdgeCases:
    """Test suite for edge cases and error handling"""
    
    @pytest.fixture
    def client(self):
        """Create a test client with authentication"""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['LOGIN_DISABLED'] = True
        with app.test_client() as client:
            yield client
    
    def test_compare_case_insensitive(self, client):
        """Test that player names are case-insensitive"""
        response1 = client.post('/api/players/compare',
                               json={'players': ['lautaro martinez', 'victor osimhen']},
                               content_type='application/json')
        
        response2 = client.post('/api/players/compare',
                               json={'players': ['LAUTARO MARTINEZ', 'VICTOR OSIMHEN']},
                               content_type='application/json')
        
        # Both should succeed or fail consistently
        assert response1.status_code == response2.status_code
    
    def test_compare_with_spaces(self, client):
        """Test player names with leading/trailing spaces"""
        response = client.post('/api/players/compare',
                              json={'players': ['  Lautaro Martinez  ', '  Victor Osimhen  ']},
                              content_type='application/json')
        
        # Should handle spaces gracefully
        if response.status_code == 200:
            data = response.get_json()
            assert data['success'] is True
    
    def test_compare_duplicate_players(self, client):
        """Test comparison with duplicate player names"""
        response = client.post('/api/players/compare',
                              json={'players': ['Lautaro Martinez', 'Lautaro Martinez']},
                              content_type='application/json')
        
        # Should either deduplicate or return error
        assert response.status_code in [200, 400]


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
