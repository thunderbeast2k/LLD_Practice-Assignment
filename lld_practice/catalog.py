"""Problem catalogue. Each problem = learner-facing brief + evaluator-facing rubric.

The rubric describes *concepts* (with aliases), not one reference solution, so several
valid designs can score well.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .domain import NotFoundError


@dataclass(frozen=True)
class Entity:
    name: str
    aliases: tuple
    hint: str
    required: bool = True


@dataclass(frozen=True)
class Behaviour:
    id: str
    description: str
    keywords: tuple          # method-name words that indicate the behaviour is modelled
    owners: tuple = ()       # concepts that are natural (not the only) homes for it


@dataclass(frozen=True)
class VariationPoint:
    id: str
    title: str
    aliases: tuple
    scenario: str            # "What if ...?" extension question shown in feedback


@dataclass(frozen=True)
class Problem:
    id: str
    title: str
    difficulty: str
    summary: str
    requirements: tuple
    assumptions: tuple
    thinking_prompts: tuple
    entities: tuple = field(default=())
    behaviours: tuple = field(default=())
    variation_points: tuple = field(default=())

    def public(self, detail: bool = True) -> dict:
        d = {"id": self.id, "title": self.title, "difficulty": self.difficulty,
             "summary": self.summary}
        if detail:
            d.update(requirements=list(self.requirements), assumptions=list(self.assumptions),
                     thinking_prompts=list(self.thinking_prompts))
        return d


PROBLEMS = (
    Problem(
        id="parking-lot", title="Parking Lot", difficulty="Easy",
        summary="Design a multi-floor parking lot that issues tickets and charges on exit.",
        requirements=(
            "The lot has multiple floors; each floor has spots of different sizes (compact, regular, large).",
            "Vehicles (motorcycle, car, truck) enter, get an available suitable spot, and receive a ticket.",
            "On exit the vehicle presents the ticket, pays a fee based on time parked, and the spot is freed.",
            "The lot reports whether it is full.",
            "Pricing rules and spot-selection rules must be easy to change (e.g. hourly vs. flat, nearest vs. cheapest).",
        ),
        assumptions=("Single entrance/exit is fine.", "Payment gateway integration is out of scope."),
        thinking_prompts=(
            "Who owns the decision 'which spot does this vehicle get'?",
            "What changes when a new vehicle type or a new pricing rule is added?",
            "What is a Ticket: a receipt, a session, or both?",
        ),
        entities=(
            Entity("Parking lot", ("parkinglot", "garage", "lot", "carpark", "parkingsystem"),
                   "The aggregate/entry point that coordinates parking and exit."),
            Entity("Parking spot", ("spot", "slot", "space", "bay"),
                   "Something that can be occupied and has a size/type."),
            Entity("Vehicle", ("vehicle", "car", "bike", "motorcycle", "truck"),
                   "What gets parked; size/type drives which spot fits."),
            Entity("Ticket", ("ticket", "receipt", "session", "parkingrecord"),
                   "Links a vehicle, a spot and entry time so the fee can be computed."),
            Entity("Floor / level", ("floor", "level", "zone"), "Groups spots.", required=False),
            Entity("Payment", ("payment", "invoice", "bill"), "Records the fee paid.", required=False),
        ),
        behaviours=(
            Behaviour("park", "Park a vehicle (find a spot, issue a ticket)",
                      ("park", "enter", "entry", "admit", "assign", "allocate", "issue"),
                      ("lot", "garage", "system")),
            Behaviour("unpark", "Exit / unpark and free the spot",
                      ("unpark", "exit", "leave", "checkout", "release", "vacate", "free"),
                      ("lot", "garage", "system")),
            Behaviour("fee", "Calculate the fee from the time parked",
                      ("fee", "price", "pricing", "charge", "cost", "amount", "calculate", "bill"),
                      ("pricing", "fee", "rate", "ticket", "payment", "lot")),
            Behaviour("availability", "Find an available spot / report full",
                      ("available", "find", "isfull", "full", "free", "vacant"),
                      ("lot", "floor", "level", "spot", "allocator", "strategy")),
        ),
        variation_points=(
            VariationPoint("pricing", "Pricing rules",
                           ("pricing", "fee", "rate", "tariff", "charge", "pricer", "payment"),
                           "Weekend pricing or per-vehicle-type rates are introduced."),
            VariationPoint("allocation", "Spot selection",
                           ("allocation", "allocator", "assignment", "assigner", "selection",
                            "selector", "spotfinder", "finder", "strategy"),
                           "Operators want 'nearest to entrance' instead of 'first free'."),
            VariationPoint("vehicle", "Vehicle types",
                           ("vehicle", "vehicletype", "vehiclesize"),
                           "A new vehicle type (e.g. electric car needing a charger) is added."),
        ),
    ),
    Problem(
        id="elevator", title="Elevator System", difficulty="Medium",
        summary="Design a bank of elevators serving a building, including request scheduling.",
        requirements=(
            "A building has N floors and M elevators.",
            "Passengers press hall buttons (up/down) outside and floor buttons inside the elevator.",
            "A scheduler assigns hall requests to an elevator.",
            "Each elevator moves, stops at requested floors, and opens/closes its door.",
            "The scheduling algorithm must be replaceable (e.g. nearest car, zoning, SCAN).",
        ),
        assumptions=("No weight limit or emergency modes.", "Time can be simulated with discrete steps."),
        thinking_prompts=(
            "Who knows the elevator's current floor and direction - and who decides what it does next?",
            "How do you model 'idle / moving up / moving down / door open' without a tangle of ifs?",
            "Is an inside-button press the same kind of thing as a hall call?",
        ),
        entities=(
            Entity("Elevator", ("elevator", "cab", "lift", "car"), "A single car with its own state."),
            Entity("Controller / scheduler", ("controller", "scheduler", "dispatcher", "system", "bank"),
                   "Coordinates several elevators and assigns requests."),
            Entity("Request", ("request", "call", "task", "command"), "A press of a button for a floor."),
            Entity("Direction / state", ("direction", "state", "status"),
                   "Idle/up/down - an enum or a state hierarchy.", required=False),
            Entity("Door", ("door",), "Open/close behaviour.", required=False),
            Entity("Button / panel", ("button", "panel"), "Hall and cabin buttons.", required=False),
        ),
        behaviours=(
            Behaviour("request", "Accept a request (hall call / floor select)",
                      ("request", "call", "press", "select", "submit"), ("controller", "scheduler", "button", "elevator")),
            Behaviour("dispatch", "Assign a request to an elevator",
                      ("dispatch", "assign", "schedule", "choose", "select", "pick"), ("controller", "scheduler", "dispatcher", "strategy")),
            Behaviour("move", "Move / step towards a floor",
                      ("move", "step", "tick", "goto", "run", "advance", "moveto"), ("elevator", "cab")),
            Behaviour("door", "Open/close the door at a stop",
                      ("open", "close", "door", "stop"), ("elevator", "door", "cab")),
        ),
        variation_points=(
            VariationPoint("scheduling", "Scheduling algorithm",
                           ("scheduling", "scheduler", "dispatch", "dispatcher", "strategy", "algorithm", "scan", "look"),
                           "Product wants zoned scheduling for a high-rise."),
            VariationPoint("state", "Elevator state",
                           ("state", "direction", "status"),
                           "A new state such as 'maintenance' or 'out of service' appears."),
        ),
    ),
    Problem(
        id="vending-machine", title="Vending Machine", difficulty="Medium",
        summary="Design a vending machine that sells products for coins and cash.",
        requirements=(
            "The machine stocks products in slots with a price and quantity.",
            "A user inserts money, selects a product, and the machine dispenses it and returns change.",
            "The user can cancel and get a refund before the product is dispensed.",
            "Operators can restock products.",
            "Behaviour depends on what has happened so far (idle, has money, dispensing, out of service).",
        ),
        assumptions=("Only one transaction at a time.", "Card payments are a future extension."),
        thinking_prompts=(
            "What are the legal actions in each machine state - and where does that logic live?",
            "What changes when card payment is added?",
            "Who owns stock counts: the machine, an inventory, or the slot?",
        ),
        entities=(
            Entity("Vending machine", ("vendingmachine", "machine", "vendor"), "Entry point for user actions."),
            Entity("Product", ("product", "item", "snack", "goods"), "What is sold; has a price."),
            Entity("Inventory / slot", ("inventory", "stock", "slot", "shelf", "rack"), "Tracks quantity per product."),
            Entity("Payment / money", ("payment", "coin", "cash", "money", "wallet", "balance"),
                   "Tracks inserted money and change.", required=False),
            Entity("State", ("state",), "Machine states.", required=False),
        ),
        behaviours=(
            Behaviour("select", "Select a product", ("select", "choose", "pick"), ("machine", "state")),
            Behaviour("insert", "Insert money", ("insert", "pay", "coin", "money", "deposit", "addmoney"), ("machine", "state", "payment")),
            Behaviour("dispense", "Dispense the product", ("dispense", "deliver", "vend", "release"), ("machine", "state")),
            Behaviour("refund", "Refund / return change", ("refund", "change", "cancel", "return"), ("machine", "state", "payment")),
            Behaviour("restock", "Restock inventory", ("restock", "refill", "addstock", "addproduct", "replenish"), ("inventory", "machine", "slot")),
        ),
        variation_points=(
            VariationPoint("state", "Machine state", ("state", "status", "idle"),
                           "A new 'out of service' state must block coin insertion."),
            VariationPoint("payment", "Payment method", ("payment", "paymentmethod", "method", "tender"),
                           "Card/UPI payment is added next quarter."),
        ),
    ),
    Problem(
        id="library", title="Library Management", difficulty="Easy",
        summary="Design a library where members borrow and return books and pay late fines.",
        requirements=(
            "The library holds books; each book can have several physical copies.",
            "Members borrow copies (with a maximum number of active loans) and return them.",
            "Overdue returns incur a fine.",
            "Members can search the catalogue by title or author.",
            "Fine rules and search criteria should be extensible.",
        ),
        assumptions=("No online payments.", "Reservations are optional."),
        thinking_prompts=(
            "What's the difference between a Book and a physical copy of a book?",
            "Is a Loan just a relationship, or does it have behaviour (due date, fine)?",
            "How would you add search by ISBN without touching existing code?",
        ),
        entities=(
            Entity("Library", ("library", "catalog", "catalogue"), "Coordinates catalogue, members and loans."),
            Entity("Book", ("book", "title", "publication"), "Bibliographic information."),
            Entity("Member", ("member", "patron", "user", "borrower"), "Someone who borrows."),
            Entity("Loan", ("loan", "lending", "borrowing", "checkout", "issue", "transaction"),
                   "A borrowing of a copy by a member with a due date."),
            Entity("Book copy", ("copy", "bookitem", "item", "specimen"), "A physical copy.", required=False),
            Entity("Fine", ("fine", "penalty"), "Late fee.", required=False),
        ),
        behaviours=(
            Behaviour("borrow", "Borrow a book", ("borrow", "checkout", "check", "issue", "lend"), ("library", "member", "loan")),
            Behaviour("return", "Return a book", ("return", "checkin", "giveback"), ("library", "member", "loan")),
            Behaviour("search", "Search the catalogue", ("search", "find", "lookup", "query", "filter"), ("library", "catalog", "search")),
            Behaviour("fine", "Compute a fine for late returns", ("fine", "penalty", "overdue", "late", "calculate"), ("fine", "loan", "policy", "library")),
        ),
        variation_points=(
            VariationPoint("fine", "Fine policy", ("fine", "penalty", "policy"),
                           "Fines differ for students vs. staff, or become capped."),
            VariationPoint("search", "Search criteria", ("search", "filter", "criteria", "query", "specification"),
                           "Search by ISBN or publisher must be added without editing Library."),
        ),
    ),
)


class ProblemCatalog:
    def __init__(self, problems=PROBLEMS):
        self._problems = {p.id: p for p in problems}

    def list(self) -> list:
        return list(self._problems.values())

    def get(self, problem_id: str) -> Problem:
        try:
            return self._problems[problem_id]
        except KeyError:
            raise NotFoundError(f"Unknown problem '{problem_id}'.")
