from convergence_games.services.algorithm.game_allocator import GameAllocator, is_valid_allocation
from convergence_games.services.algorithm.mock_data import (
    DefaultPartyGenerator,
    DefaultSessionGenerator,
    MockDataGenerator,
)

if __name__ == "__main__":
    # End to End
    mock_data_generator = MockDataGenerator(
        session_generator=DefaultSessionGenerator(), party_generator=DefaultPartyGenerator()
    )
    sessions, parties = mock_data_generator.create_scenario(
        session_count=3,
        party_count=10,
    )
    game_allocator = GameAllocator()
    results = game_allocator.allocate(sessions, parties)
    print(results)
    print("---")
    valid = is_valid_allocation(sessions, parties, results)
    print(f"Allocation valid: {valid}")
