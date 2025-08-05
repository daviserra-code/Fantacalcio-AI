
"""
Strutture dati e utilities per il fantacalcio
"""

class Player:
    def __init__(self, name, team, role, price=0, fantamedia=0, appearances=0):
        self.name = name
        self.team = team
        self.role = role  # P, D, C, A
        self.price = price
        self.fantamedia = fantamedia
        self.appearances = appearances
        self.xg = 0  # Expected goals
        self.xa = 0  # Expected assists
        self.minutes_played = 0
        self.ownership_percentage = 0

class League:
    def __init__(self, league_type="Classic", participants=8, budget=500):
        self.league_type = league_type  # Classic, Mantra, Draft, Superscudetto
        self.participants = participants
        self.budget = budget
        self.rules = self.get_default_rules()
    
    def get_default_rules(self):
        """Get default rules based on league type"""
        base_rules = {
            "portieri": 3,
            "difensori": 8,
            "centrocampisti": 8,
            "attaccanti": 6,
            "formazione": "3-5-2 o varianti"
        }
        
        if self.league_type == "Mantra":
            base_rules["modificatori_mantra"] = True
            base_rules["bonus_assist"] = 1
            base_rules["bonus_clean_sheet"] = 1
        
        elif self.league_type == "Draft":
            base_rules["budget"] = 0  # No budget in draft
            base_rules["snake_draft"] = True
        
        return base_rules

class AuctionHelper:
    def __init__(self, league):
        self.league = league
        self.spent_budget = 0
        self.remaining_budget = league.budget
        self.players_bought = {"P": 0, "D": 0, "C": 0, "A": 0}
    
    def suggest_bid(self, player, current_bid):
        """Suggest optimal bid for a player"""
        max_recommended = self.calculate_max_bid(player)
        
        if current_bid >= max_recommended:
            return {"action": "PASSA", "reason": f"Prezzo troppo alto (max consigliato: {max_recommended})"}
        
        next_bid = current_bid + 1
        return {
            "action": "RILANCIA", 
            "suggested_bid": next_bid,
            "max_bid": max_recommended,
            "reason": f"Giocatore interessante fino a {max_recommended}"
        }
    
    def calculate_max_bid(self, player):
        """Calculate maximum recommended bid"""
        # Simplified calculation - in real app would use complex algorithms
        base_value = player.fantamedia * 3
        role_multiplier = {"P": 0.8, "D": 0.9, "C": 1.0, "A": 1.2}
        
        return int(base_value * role_multiplier.get(player.role, 1.0))

# Sample data for testing
SAMPLE_PLAYERS = [
    Player("Donnarumma", "PSG", "P", fantamedia=6.5, appearances=30),
    Player("Bastoni", "Inter", "D", fantamedia=6.2, appearances=32),
    Player("Barella", "Inter", "C", fantamedia=6.8, appearances=28),
    Player("Osimhen", "Napoli", "A", fantamedia=7.2, appearances=25)
]
