import argparse
import random

from src.llm.client import FakeLLMClient, TransformersLLMClient
from src.simulation.engine import SimulationEngine
from src.utils.clear_run import clear_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the LLM-Town simulation."
    )

    parser.add_argument(
        "--agents-path",
        default="data/agents.json",
        help="Path to the agents JSON file.",
    )

    parser.add_argument(
        "--locations-path",
        default="data/locations.json",
        help="Path to the locations JSON file.",
    )

    parser.add_argument(
        "--days",
        type=int,
        default=25,
        help="Number of days to simulate.",
    )

    parser.add_argument(
        "--hours",
        type=int,
        nargs="+",
        default=[8, 12, 18, 22],
        help="Hours to simulate each day. Example: --hours 8 12 18 22",
    )

    parser.add_argument(
        "--load-state",
        action="store_true",
        help="Load the saved simulation state from data/save_state.json.",
    )

    parser.add_argument(
        "--fake-llm",
        action="store_true",
        help="Use FakeLLMClient instead of loading a transformer model.",
    )

    parser.add_argument(
        "--model-name",
        default="Qwen/Qwen2.5-3B-Instruct",
        help="Hugging Face model name to use when not using --fake-llm.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible simulation behavior.",
    )

    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear previous logs/output before running.",
    )

    return parser.parse_args()


def build_llm_client(args: argparse.Namespace):
    if args.fake_llm:
        return FakeLLMClient()

    return TransformersLLMClient(model_name=args.model_name)


def main() -> None:
    args = parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if not args.no_clear:
        clear_run()

    llm_client = build_llm_client(args)

    engine = SimulationEngine(
        agents_path=args.agents_path,
        locations_path=args.locations_path,
        load_state=args.load_state,
        llm_client=llm_client,
    )

    engine.run(days=args.days, hours=args.hours)


if __name__ == "__main__":
    main()