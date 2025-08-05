
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
        self.injury_risk = 0  # 0-10 scale
        self.form_trend = 0  # Recent form direction
        self.fixtures_difficulty = 0  # Upcoming fixtures difficulty
    
    def value_score(self) -> float:
        """Calculate value for money score"""
        if self.price == 0:
            return 0
        return (self.fantamedia * self.appearances) / self.price
    
    def consistency_score(self) -> float:
        """Calculate consistency based on appearances and fantamedia"""
        if self.appearances == 0:
            return 0
        consistency = (self.appearances / 38) * (self.fantamedia / 10)
        return min(consistency, 1.0)
    
    def compare_with(self, other_player) -> Dict:
        """Detailed comparison with another player"""
        if self.role != other_player.role:
            return {"error": "Cannot compare players of different roles"}
        
        comparison = {
            "player_a": self.name,
            "player_b": other_player.name,
            "role": self.role,
            "winner": {},
            "metrics": {}
        }
        
        metrics = [
            ("fantamedia", "Fantamedia"),
            ("price", "Prezzo", True),  # Lower is better
            ("appearances", "Presenze"),
            ("value_score", "Rapporto Qualità/Prezzo"),
            ("consistency_score", "Continuità")
        ]
        
        for metric_attr, metric_name, *lower_better in metrics:
            is_lower_better = len(lower_better) > 0
            
            if hasattr(self, metric_attr):
                val_a = getattr(self, metric_attr)() if callable(getattr(self, metric_attr)) else getattr(self, metric_attr)
                val_b = getattr(other_player, metric_attr)() if callable(getattr(other_player, metric_attr)) else getattr(other_player, metric_attr)
            else:
                continue
            
            comparison["metrics"][metric_name] = {
                self.name: val_a,
                other_player.name: val_b
            }
            
            if is_lower_better:
                winner = self.name if val_a < val_b else other_player.name
            else:
                winner = self.name if val_a > val_b else other_player.name
            
            comparison["winner"][metric_name] = winner
        
        return comparison

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
    # Goalkeepers
    Player("Donnarumma", "PSG", "P", fantamedia=6.5, appearances=30, price=25),
    Player("Maignan", "Milan", "P", fantamedia=6.3, appearances=28, price=22),
    Player("Szczesny", "Juventus", "P", fantamedia=6.1, appearances=32, price=20),
    Player("Handanovic", "Inter", "P", fantamedia=5.9, appearances=25, price=18),
    Player("Meret", "Napoli", "P", fantamedia=6.0, appearances=22, price=15),
    
    # Defenders
    Player("Bastoni", "Inter", "D", fantamedia=6.2, appearances=32, price=28),
    Player("Theo Hernandez", "Milan", "D", fantamedia=6.8, appearances=30, price=32),
    Player("Cuadrado", "Juventus", "D", fantamedia=6.4, appearances=28, price=26),
    Player("Di Lorenzo", "Napoli", "D", fantamedia=6.1, appearances=33, price=24),
    Player("Spinazzola", "Roma", "D", fantamedia=6.0, appearances=20, price=22),
    Player("Acerbi", "Inter", "D", fantamedia=6.2, appearances=29, price=20),
    Player("Tomori", "Milan", "D", fantamedia=6.0, appearances=31, price=18),
    
    # Midfielders
    Player("Barella", "Inter", "C", fantamedia=6.8, appearances=28, price=35),
    Player("Milinkovic-Savic", "Lazio", "C", fantamedia=6.9, appearances=32, price=38),
    Player("Tonali", "Milan", "C", fantamedia=6.3, appearances=30, price=28),
    Player("Locatelli", "Juventus", "C", fantamedia=6.1, appearances=29, price=25),
    Player("Pellegrini", "Roma", "C", fantamedia=6.5, appearances=26, price=30),
    Player("Zaniolo", "Roma", "C", fantamedia=6.2, appearances=24, price=28),
    Player("Kvaratskhelia", "Napoli", "C", fantamedia=7.1, appearances=31, price=42),
    Player("Leao", "Milan", "C", fantamedia=6.7, appearances=30, price=38),
    
    # Forwards
    Player("Osimhen", "Napoli", "A", fantamedia=7.2, appearances=25, price=45),
    Player("Vlahovic", "Juventus", "A", fantamedia=6.8, appearances=28, price=40),
    Player("Lautaro", "Inter", "A", fantamedia=6.9, appearances=30, price=42),
    Player("Giroud", "Milan", "A", fantamedia=6.6, appearances=26, price=35),
    Player("Abraham", "Roma", "A", fantamedia=6.4, appearances=24, price=32),
    Player("Immobile", "Lazio", "A", fantamedia=6.7, appearances=29, price=38),
    Player("Dzeko", "Inter", "A", fantamedia=6.3, appearances=27, price=30),
    Player("Belotti", "Roma", "A", fantamedia=6.0, appearances=22, price=25)
]
