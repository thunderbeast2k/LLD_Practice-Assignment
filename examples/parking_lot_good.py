from abc import ABC, abstractmethod
from enum import Enum


class VehicleType(Enum):
    MOTORCYCLE = 1
    CAR = 2
    TRUCK = 3


class Vehicle(ABC):
    def __init__(self, plate: str):
        self.plate = plate

    @abstractmethod
    def type(self) -> VehicleType: ...


class Car(Vehicle):
    def type(self): return VehicleType.CAR


class Motorcycle(Vehicle):
    def type(self): return VehicleType.MOTORCYCLE


class ParkingSpot:
    def __init__(self, number: int, spot_type: VehicleType):
        self.number, self.spot_type, self.vehicle = number, spot_type, None

    def can_fit(self, vehicle: Vehicle) -> bool: ...
    def occupy(self, vehicle: Vehicle) -> None: ...
    def vacate(self) -> None: ...
    def is_free(self) -> bool: ...


class Floor:
    def __init__(self, spots: list[ParkingSpot]):
        self.spots = spots

    def find_available(self, vehicle: Vehicle) -> ParkingSpot: ...


class Ticket:
    def __init__(self, vehicle: Vehicle, spot: ParkingSpot, entry_time):
        self.vehicle, self.spot, self.entry_time = vehicle, spot, entry_time


class PricingStrategy(ABC):
    @abstractmethod
    def calculate_fee(self, ticket: Ticket, exit_time) -> float: ...


class HourlyPricing(PricingStrategy):
    def calculate_fee(self, ticket, exit_time): ...


class FlatRatePricing(PricingStrategy):
    def calculate_fee(self, ticket, exit_time): ...


class SpotAllocationStrategy(ABC):
    @abstractmethod
    def select(self, floors: list[Floor], vehicle: Vehicle) -> ParkingSpot: ...


class FirstFreeAllocation(SpotAllocationStrategy):
    def select(self, floors, vehicle): ...


class NearestEntranceAllocation(SpotAllocationStrategy):
    def select(self, floors, vehicle): ...


class ParkingLot:
    def __init__(self, floors: list[Floor], pricing: PricingStrategy, allocator: SpotAllocationStrategy):
        self.floors, self.pricing, self.allocator = floors, pricing, allocator

    def park(self, vehicle: Vehicle) -> Ticket: ...
    def unpark(self, ticket: Ticket) -> float: ...
    def is_full(self) -> bool: ...
