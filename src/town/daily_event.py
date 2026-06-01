from dataclasses import dataclass
import random


@dataclass
class DailyEvent:
    id: str
    name: str
    description: str
    location_id: str
    tags: list[str]


EVENT_POOL = [
    DailyEvent(
        name="Farmers Market",
        description="Local vendors are setting up booths and selling fresh produce.",
        location_id="market",
        tags=["market", "community", "wealth"],
    ),
    DailyEvent(
        name="Book Club",
        description="Residents are gathering to discuss a new book at the library.",
        location_id="library",
        tags=["learning", "social", "community"],
    ),
    DailyEvent(
        name="Cafe Discount",
        description="The cafe is offering a discount to first-time customers.",
        location_id="cafe",
        tags=["social", "wealth"],
    ),
    DailyEvent(
        name="Town Cleanup",
        description="Volunteers are meeting to clean up the town square.",
        location_id="town_square",
        tags=["community", "social"],
    ),
    DailyEvent(
        name="Art Workshop",
        description="A local artist is teaching residents basic painting techniques.",
        location_id="library",
        tags=["art", "learning", "social"],
    ),
    DailyEvent(
        name="Street Music Night",
        description="Musicians are performing near the town square in the evening.",
        location_id="town_square",
        tags=["music", "social", "community"],
    ),
    DailyEvent(
        name="Cooking Class",
        description="Residents are learning simple recipes using local ingredients.",
        location_id="cafe",
        tags=["food", "learning", "social"],
    ),
    DailyEvent(
        name="Merchant Inspection",
        description="Market stalls are being checked for fair prices and proper records.",
        location_id="market",
        tags=["market", "wealth", "rules"],
    ),
    DailyEvent(
        name="Town Hall Meeting",
        description="Residents are discussing future plans for the town.",
        location_id="town_square",
        tags=["community", "planning", "social"],
    ),
    DailyEvent(
        name="Gardening Workshop",
        description="Volunteers are teaching residents how to grow vegetables and herbs.",
        location_id="town_square",
        tags=["community", "food", "learning"],
    ),
    DailyEvent(
        name="Library Fundraiser",
        description="The library is raising money for new books and repairs.",
        location_id="library",
        tags=["learning", "wealth", "community"],
    ),
    DailyEvent(
        name="New Bakery Opening",
        description="A bakery is opening nearby and giving out samples.",
        location_id="cafe",
        tags=["food", "market", "social"],
    ),
    DailyEvent(
        name="Volunteer Drive",
        description="The town is looking for volunteers for upcoming community projects.",
        location_id="town_square",
        tags=["community", "social"],
    ),
    DailyEvent(
        name="Repair Day",
        description="Residents are fixing benches, signs, and small public spaces.",
        location_id="town_square",
        tags=["community", "work"],
    ),
    DailyEvent(
        name="Local Sports Match",
        description="Residents are gathering to watch a friendly local sports match.",
        location_id="town_square",
        tags=["social", "community", "sports"],
    ),
    DailyEvent(
        name="School Fair",
        description="Families are visiting booths, games, and small performances.",
        location_id="town_square",
        tags=["social", "community"],
    ),
    DailyEvent(
        name="Poetry Night",
        description="Residents are sharing poems and short stories at the library.",
        location_id="library",
        tags=["learning", "art", "social"],
    ),
    DailyEvent(
        name="Supplier Visit",
        description="A traveling supplier is visiting the market with new goods.",
        location_id="market",
        tags=["market", "wealth", "business"],
    ),
    DailyEvent(
        name="Public Debate",
        description="Residents are debating a proposed change to town rules.",
        location_id="town_square",
        tags=["community", "rules", "social"],
    ),
    DailyEvent(
        name="Lost Pet Search",
        description="Several residents are helping search for a missing pet.",
        location_id="town_square",
        tags=["community", "social", "help"],
    ),
]


def choose_daily_event() -> DailyEvent:
    return random.choice(EVENT_POOL)