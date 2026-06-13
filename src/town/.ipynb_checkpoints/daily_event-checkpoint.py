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
        id="farmers_market",
        name="Farmers Market",
        description="Local vendors are setting up booths and selling fresh produce.",
        location_id="market",
        tags=["market", "community", "wealth"],
    ),
    DailyEvent(
        id="book_club",
        name="Book Club",
        description="Residents are gathering to discuss a new book at the library.",
        location_id="library",
        tags=["learning", "social", "community"],
    ),
    DailyEvent(
        id="cafe_discount",
        name="Cafe Discount",
        description="The cafe is offering a discount to first-time customers.",
        location_id="cafe",
        tags=["social", "wealth"],
    ),
    DailyEvent(
        id="town_cleanup",
        name="Town Cleanup",
        description="Volunteers are meeting to clean up the town square.",
        location_id="town_square",
        tags=["community", "social"],
    ),
    DailyEvent(
        id="art_workshop",
        name="Art Workshop",
        description="A local artist is teaching residents basic painting techniques.",
        location_id="library",
        tags=["art", "learning", "social"],
    ),
    DailyEvent(
        id="street_music_night",
        name="Street Music Night",
        description="Musicians are performing near the town square in the evening.",
        location_id="town_square",
        tags=["music", "social", "community"],
    ),
    DailyEvent(
        id="cooking_class",
        name="Cooking Class",
        description="Residents are learning simple recipes using local ingredients.",
        location_id="cafe",
        tags=["food", "learning", "social"],
    ),
    DailyEvent(
        id="merchant_inspection",
        name="Merchant Inspection",
        description="Market stalls are being checked for fair prices and proper records.",
        location_id="market",
        tags=["market", "wealth", "rules"],
    ),
    DailyEvent(
        id="town_hall_meeting",
        name="Town Hall Meeting",
        description="Residents are discussing future plans for the town.",
        location_id="town_square",
        tags=["community", "planning", "social"],
    ),
    DailyEvent(
        id="gardening_workshop",
        name="Gardening Workshop",
        description="Volunteers are teaching residents how to grow vegetables and herbs.",
        location_id="town_square",
        tags=["community", "food", "learning"],
    ),
    DailyEvent(
        id="library_fundraiser",
        name="Library Fundraiser",
        description="The library is raising money for new books and repairs.",
        location_id="library",
        tags=["learning", "wealth", "community"],
    ),
    DailyEvent(
        id="new_bakery_opening",
        name="New Bakery Opening",
        description="A bakery is opening nearby and giving out samples.",
        location_id="cafe",
        tags=["food", "market", "social"],
    ),
    DailyEvent(
        id="volunteer_drive",
        name="Volunteer Drive",
        description="The town is looking for volunteers for upcoming community projects.",
        location_id="town_square",
        tags=["community", "social"],
    ),
    DailyEvent(
        id="repair_day",
        name="Repair Day",
        description="Residents are fixing benches, signs, and small public spaces.",
        location_id="town_square",
        tags=["community", "work"],
    ),
    DailyEvent(
        id="local_sports_match",
        name="Local Sports Match",
        description="Residents are gathering to watch a friendly local sports match.",
        location_id="town_square",
        tags=["social", "community", "sports"],
    ),
    DailyEvent(
        id="school_fair",
        name="School Fair",
        description="Families are visiting booths, games, and small performances.",
        location_id="town_square",
        tags=["social", "community"],
    ),
    DailyEvent(
        id="poetry_night",
        name="Poetry Night",
        description="Residents are sharing poems and short stories at the library.",
        location_id="library",
        tags=["learning", "art", "social"],
    ),
    DailyEvent(
        id="supplier_visit",
        name="Supplier Visit",
        description="A traveling supplier is visiting the market with new goods.",
        location_id="market",
        tags=["market", "wealth", "business"],
    ),
    DailyEvent(
        id="public_debate",
        name="Public Debate",
        description="Residents are debating a proposed change to town rules.",
        location_id="town_square",
        tags=["community", "rules", "social"],
    ),
    DailyEvent(
        id="lost_pet_search",
        name="Lost Pet Search",
        description="Several residents are helping search for a missing pet.",
        location_id="town_square",
        tags=["community", "social", "help"],
    ),
]


def choose_daily_event() -> DailyEvent:
    return random.choice(EVENT_POOL)