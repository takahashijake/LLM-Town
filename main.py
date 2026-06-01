from src.simulation.engine import SimulationEngine 

def main():
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
    )

    engine.run(days=2, hours=[8, 12, 18, 22])

if __name__== "__main__":
    main()


