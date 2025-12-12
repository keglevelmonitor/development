"""
brewbrain app
profile_data.py
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional
from enum import Enum
import uuid

# --- Enums for Logic Control ---

class StepType(str, Enum):
    # Actions (Hardware Control)
    DELAYED_START = "Delayed Start" # Heats to temp by specific time
    STEP = "Step"                   # Standard Hold
    MASH = "Mash"                   # Standard Hold
    MASH_OUT = "Mash-out"           # Heat to 170F/76C
    BOIL = "Boil"                   # Power % Control
    
    # Activities (User Input / Manual Tasks)
    SG_READING = "Specific Gravity Reading"
    LAUTER = "Lauter"
    HOPS_ADJUNCTS = "Hops / Adjuncts"

class TimeoutBehavior(str, Enum):
    AUTO_ADVANCE = "Auto Advance"
    MANUAL_ADVANCE = "Manual Advance" 
    END_PROGRAM = "End Program"       

# --- Main Data Class ---

@dataclass
class BrewStep:
    """
    Represents a single step in a brewing profile.
    """
    # Identifiers
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "New Step"
    step_type: StepType = StepType.STEP
    note: str = ""
    
    # --- ACTION FIELDS ---
    
    # Target Temperature 
    setpoint_f: Optional[float] = None  
    
    # --- TIMING FIELDS ---
    
    # Duration in MINUTES
    duration_min: float = 0.0
    
    # Target-based (Specific for "Delayed Start")
    target_completion_time: Optional[str] = None
    
    # --- POWER / VOLUME ---
    
    # Power setting (Watts or %)
    power_watts: Optional[int] = None 
    
    # Volume (Specific for Lauter step)
    lauter_volume: Optional[float] = None
    
    # Temp (Specific for Lauter step)
    lauter_temp_f: Optional[float] = None

    # What happens when the timer hits zero?
    timeout_behavior: TimeoutBehavior = TimeoutBehavior.MANUAL_ADVANCE

    # --- ACTIVITY RESULT FIELDS (For Logging) ---
    sg_reading: Optional[float] = None
    sg_temp_f: Optional[float] = None
    sg_temp_correction: bool = False
    sg_corrected_value: Optional[float] = None
    
    def to_dict(self):
        return asdict(self)

@dataclass
class BrewProfile:
    """
    A collection of steps comprising a full recipe/schedule.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "New Profile"
    created_date: str = "" 
    steps: List[BrewStep] = field(default_factory=list)

    def add_step(self, step: BrewStep):
        self.steps.append(step)
        
    def remove_step(self, step_id: str):
        self.steps = [s for s in self.steps if s.id != step_id]

    def reorder_steps(self, new_order_ids: List[str]):
        """Reorders internal list based on a list of IDs passed from UI"""
        step_map = {s.id: s for s in self.steps}
        new_steps = []
        for uid in new_order_ids:
            if uid in step_map:
                new_steps.append(step_map[uid])
        
        if len(new_steps) < len(self.steps):
            for s in self.steps:
                if s.id not in new_order_ids:
                    new_steps.append(s)
                    
        self.steps = new_steps
