import argparse
import random

from src.llm.client import FakeLLMClient, TransformersLLMClient
from src.simulation.engine import SimulationEngine
from src.utils.clear_run import clear_run


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


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
        "--grounded-dialogue-tier",
        choices=["full_grounded_realization_support", "safe_degraded_support", "unverified"],
        default="unverified",
        help="Validated grounded-dialogue capability classification for this model.",
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
    parser.add_argument(
        "--max-conversation-turns", type=int, default=4,
        help="Maximum utterances in each conversation session (default: 4).",
    )
    parser.add_argument(
        "--conversation-execution", choices=["serial", "concurrent", "batched"],
        default="serial", help="Conversation realization backend (default: serial).",
    )
    parser.add_argument(
        "--conversation-workers", type=int, default=4,
        help="Maximum local realization workers in concurrent mode.",
    )
    parser.add_argument(
        "--conversation-batch-size", type=positive_int, default=4,
        help="Maximum requests in each local-model generation batch.",
    )

    return parser.parse_args()


def build_llm_client(args: argparse.Namespace):
    if args.fake_llm:
        return FakeLLMClient()

    return TransformersLLMClient(
        model_name=args.model_name,
        grounded_dialogue_capability_tier=args.grounded_dialogue_tier,
    )


def main() -> None:
    args = parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if not args.no_clear:
        clear_run()

    llm_client = build_llm_client(args)
    print(
        "Grounded dialogue capability tier: "
        f"{llm_client.grounded_dialogue_capability_tier}"
    )

    engine = SimulationEngine(
        agents_path=args.agents_path,
        locations_path=args.locations_path,
        load_state=args.load_state,
        llm_client=llm_client,
        max_conversation_turns=args.max_conversation_turns,
        conversation_execution=args.conversation_execution,
        conversation_workers=args.conversation_workers,
        conversation_batch_size=args.conversation_batch_size,
        simulation_seed=args.seed or 0,
    )

    engine.run(days=args.days, hours=args.hours)


if __name__ == "__main__":
    main()
