from src.simulation.engine import SimulationEngine 
from src.utils.clear_run import clear_run 

def main():
    clear_run()
    
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
    )

    engine.run(days=25, hours=[8, 12, 18, 22])

if __name__== "__main__":
    main()


