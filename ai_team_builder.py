# ai_team_builder.py - AI-powered team optimization
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import random

LOG = logging.getLogger("ai_team_builder")

@dataclass
class Player:
    """Player data class"""
    name: str
    role: str  # P, D, C, A
    team: str
    price: int
    fantamedia: float
    appearances: int
    goals: int = 0
    assists: int = 0
    
    @property
    def value_score(self) -> float:
        """Points per credit efficiency"""
        return (self.fantamedia / self.price) if self.price > 0 else 0
    
    @property
    def reliability_score(self) -> float:
        """How reliable is this player (0-1)"""
        max_appearances = 38
        return min(self.appearances / max_appearances, 1.0) if max_appearances > 0 else 0

class AITeamBuilder:
    """AI-powered team builder with multi-objective optimization"""
    
    def __init__(self, players: List[Player], budget: int):
        self.players = players
        self.budget = budget
        self.population_size = 100
        self.generations = 50
        self.mutation_rate = 0.15
        
    def build_optimal_team(
        self, 
        formation: Dict[str, int],
        objectives: Dict[str, float] = None
    ) -> Dict:
        """
        Build optimal team using genetic algorithm
        
        Args:
            formation: {'P': 1, 'D': 4, 'C': 4, 'A': 2} or string like "3-5-2"
            objectives: {'performance': 0.5, 'value': 0.3, 'reliability': 0.2}
        """
        if objectives is None:
            objectives = {'performance': 0.5, 'value': 0.3, 'reliability': 0.2}
        
        # Handle string formation input (e.g., "3-5-2")
        if isinstance(formation, str):
            parts = formation.split('-')
            if len(parts) == 3:
                formation = {
                    'P': 1,
                    'D': int(parts[0]),
                    'C': int(parts[1]),
                    'A': int(parts[2])
                }
            else:
                LOG.error(f"Invalid formation string: {formation}")
                formation = {'P': 1, 'D': 4, 'C': 4, 'A': 2}  # Default
        
        LOG.info(f"Building team with formation {formation}, budget {self.budget}")
        
        # Initialize population
        population = self._initialize_population(formation)
        
        best_team = None
        best_score = -float('inf')
        
        for generation in range(self.generations):
            # Evaluate fitness
            scores = [self._fitness(team, objectives) for team in population]
            
            # Track best
            max_score = max(scores)
            if max_score > best_score:
                best_score = max_score
                best_team = population[scores.index(max_score)]
                LOG.debug(f"Gen {generation}: Best score {best_score:.2f}")
            
            # Selection and reproduction
            population = self._evolve_population(population, scores)
        
        return self._format_team_result(best_team, best_score, objectives)
    
    def _initialize_population(self, formation: Dict[str, int]) -> List[List[Player]]:
        """Create initial random population"""
        population = []
        
        for _ in range(self.population_size):
            team = []
            remaining_budget = self.budget
            
            for role, count in formation.items():
                role_players = [p for p in self.players if p.role == role]
                
                # Random selection with budget constraint
                selected = []
                attempts = 0
                while len(selected) < count and attempts < 100:
                    player = random.choice(role_players)
                    if player not in selected and player.price <= remaining_budget:
                        selected.append(player)
                        remaining_budget -= player.price
                    attempts += 1
                
                team.extend(selected)
            
            if len(team) == sum(formation.values()):
                population.append(team)
        
        # Fill population if needed
        while len(population) < self.population_size:
            population.append(population[0][:])  # Duplicate first team
        
        return population
    
    def _fitness(self, team: List[Player], objectives: Dict[str, float]) -> float:
        """Calculate team fitness score"""
        if not team or self._get_team_cost(team) > self.budget:
            return -1000  # Invalid team
        
        # Check max players per team constraint (max 3 per team)
        team_counts = {}
        for player in team:
            team_counts[player.team] = team_counts.get(player.team, 0) + 1
        
        max_per_team = max(team_counts.values()) if team_counts else 0
        if max_per_team > 3:
            # Heavy penalty for exceeding limit
            return -500 - (max_per_team - 3) * 100
        
        # Performance score
        performance = sum(p.fantamedia for p in team) / len(team) if team else 0
        
        # Value score (efficiency)
        value = sum(p.value_score for p in team) / len(team) if team else 0
        
        # Reliability score
        reliability = sum(p.reliability_score for p in team) / len(team) if team else 0
        
        # Combined fitness
        fitness = (
            objectives.get('performance', 0.5) * performance +
            objectives.get('value', 0.3) * value * 10 +  # Scale up
            objectives.get('reliability', 0.2) * reliability * 50  # Scale up
        )
        
        # Bonus for budget efficiency (using more budget is better)
        budget_usage = self._get_team_cost(team) / self.budget
        fitness += budget_usage * 5
        
        # Bonus for team diversity (prefer 2-3 players per team max)
        if max_per_team <= 3:
            diversity_bonus = (4 - max_per_team) * 2  # Reward more balanced teams
            fitness += diversity_bonus
        
        return fitness
    
    def _evolve_population(
        self, 
        population: List[List[Player]], 
        scores: List[float]
    ) -> List[List[Player]]:
        """Evolve population through selection, crossover, mutation"""
        new_population = []
        
        # Elitism: keep top 10%
        elite_count = max(1, self.population_size // 10)
        elite_indices = np.argsort(scores)[-elite_count:]
        new_population.extend([population[i] for i in elite_indices])
        
        # Generate rest through crossover and mutation
        while len(new_population) < self.population_size:
            # Tournament selection
            parent1 = self._tournament_select(population, scores)
            parent2 = self._tournament_select(population, scores)
            
            # Crossover
            child = self._crossover(parent1, parent2)
            
            # Mutation
            if random.random() < self.mutation_rate:
                child = self._mutate(child)
            
            new_population.append(child)
        
        return new_population
    
    def _tournament_select(
        self, 
        population: List[List[Player]], 
        scores: List[float], 
        tournament_size: int = 3
    ) -> List[Player]:
        """Tournament selection"""
        indices = random.sample(range(len(population)), tournament_size)
        best_idx = max(indices, key=lambda i: scores[i])
        return population[best_idx]
    
    def _crossover(self, parent1: List[Player], parent2: List[Player]) -> List[Player]:
        """Single-point crossover"""
        if len(parent1) != len(parent2):
            return parent1[:]
        
        point = random.randint(1, len(parent1) - 1)
        child = parent1[:point] + parent2[point:]
        
        # Remove duplicates
        seen = set()
        unique_child = []
        for p in child:
            if p.name not in seen:
                seen.add(p.name)
                unique_child.append(p)
        
        return unique_child if len(unique_child) == len(parent1) else parent1[:]
    
    def _mutate(self, team: List[Player]) -> List[Player]:
        """Random mutation - swap one player"""
        if not team:
            return team
        
        mutated = team[:]
        idx = random.randint(0, len(mutated) - 1)
        player_to_replace = mutated[idx]
        
        # Find replacement of same role
        role_players = [p for p in self.players if p.role == player_to_replace.role]
        replacement = random.choice(role_players)
        
        mutated[idx] = replacement
        return mutated
    
    def _get_team_cost(self, team: List[Player]) -> int:
        """Calculate total team cost"""
        return sum(p.price for p in team)
    
    def _format_team_result(
        self, 
        team: List[Player], 
        score: float, 
        objectives: Dict[str, float]
    ) -> Dict:
        """Format team result for API response"""
        return {
            'team': [
                {
                    'name': p.name,
                    'role': p.role,
                    'team': p.team,
                    'price': p.price,
                    'fantamedia': p.fantamedia,
                    'value_score': round(p.value_score, 2),
                    'reliability': round(p.reliability_score, 2)
                }
                for p in team
            ],
            'total_cost': self._get_team_cost(team),
            'remaining_budget': self.budget - self._get_team_cost(team),
            'fitness_score': round(score, 2),
            'avg_fantamedia': round(sum(p.fantamedia for p in team) / len(team), 2) if team else 0,
            'formation_breakdown': self._get_formation_breakdown(team),
            'optimization_objectives': objectives,
            'recommendations': self._generate_recommendations(team)
        }
    
    def _get_formation_breakdown(self, team: List[Player]) -> Dict:
        """Get team composition by role"""
        breakdown = {'P': [], 'D': [], 'C': [], 'A': []}
        for player in team:
            breakdown[player.role].append(player.name)
        return {role: len(players) for role, players in breakdown.items()}
    
    def _generate_recommendations(self, team: List[Player]) -> List[str]:
        """Generate improvement recommendations"""
        recommendations = []
        
        # Check budget utilization
        utilization = (self._get_team_cost(team) / self.budget) * 100
        if utilization < 90:
            recommendations.append(
                f"💰 Stai usando solo il {utilization:.0f}% del budget. "
                "Considera giocatori più forti."
            )
        
        # Check reliability
        avg_reliability = sum(p.reliability_score for p in team) / len(team) if team else 0
        if avg_reliability < 0.7:
            recommendations.append(
                "⚠️ Alcuni giocatori hanno basso minutaggio. "
                "Considera alternative più affidabili."
            )
        
        # Check value efficiency
        avg_value = sum(p.value_score for p in team) / len(team) if team else 0
        if avg_value < 2.0:
            recommendations.append(
                "📊 Il rapporto qualità/prezzo può essere migliorato. "
                "Cerca giocatori con maggior fantamedia per credito."
            )
        
        return recommendations if recommendations else ["✅ Squadra ben ottimizzata!"]

def suggest_team_improvements(
    current_team: List[Dict],
    all_players: List[Player],
    budget_available: int
) -> List[Dict]:
    """Suggest specific player swaps to improve team"""
    suggestions = []
    
    for player_data in current_team:
        current_player_name = player_data['name']
        current_player = next((p for p in all_players if p.name == current_player_name), None)
        
        if not current_player:
            continue
        
        # Find better alternatives
        role_players = [p for p in all_players 
                       if p.role == current_player.role 
                       and p.name != current_player.name
                       and p.price <= current_player.price + budget_available]
        
        # Sort by value score
        better_players = sorted(role_players, key=lambda p: p.value_score, reverse=True)[:3]
        
        for better_player in better_players:
            if better_player.value_score > current_player.value_score:
                suggestions.append({
                    'type': 'swap',
                    'out': current_player.name,
                    'in': better_player.name,
                    'reason': f"Migliore rapporto qualità/prezzo: {better_player.value_score:.2f} vs {current_player.value_score:.2f}",
                    'cost_diff': better_player.price - current_player.price,
                    'performance_gain': better_player.fantamedia - current_player.fantamedia
                })
    
    return sorted(suggestions, key=lambda x: x['performance_gain'], reverse=True)[:5]
