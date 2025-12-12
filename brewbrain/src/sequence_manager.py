"""
src/sequence_manager.py
"""
import time
import threading
from datetime import datetime, timedelta
from enum import Enum
from profile_data import BrewProfile, BrewStep, StepType, TimeoutBehavior
from brew_types import StepPhase

class SequenceStatus(str, Enum):
    IDLE = "Idle"
    RUNNING = "Running"
    PAUSED = "Paused"
    WAITING_FOR_USER = "Waiting for User"
    COMPLETED = "Completed"

class SequenceManager:
    def __init__(self, settings_manager, relay_control, hardware_interface):
        self.settings = settings_manager
        self.relay = relay_control
        self.hw = hardware_interface
        
        # State Variables
        self.current_profile: BrewProfile = None
        self.current_step_index: int = -1
        self.status: SequenceStatus = SequenceStatus.IDLE
        
        # Alert Text (For UI)
        self.current_alert_text: str = ""
        
        # Timing Variables
        self.step_start_time: float = 0.0
        self.pause_start_time: float = 0.0
        self.accumulated_pause_time: float = 0.0
        
        # Smart Ramp Specifics
        self.smart_ramp_active: bool = False
        
        # Threading for the "Tick" loop
        self.stop_event = threading.Event()
        self.worker_thread = None

        # Load recovery data on boot
        self._check_recovery()

    # --- PUBLIC CONTROL METHODS ---

    def load_profile(self, profile: BrewProfile):
        self.stop()
        self.current_profile = profile
        self.current_step_index = 0
        self.status = SequenceStatus.IDLE
        self.current_alert_text = ""
        
        for s in self.current_profile.steps:
            if hasattr(s, 'reset'): s.reset()
        
        self._save_state()

    def start_sequence(self):
        if not self.current_profile: return
        
        self.status = SequenceStatus.RUNNING
        self.step_start_time = time.time()
        self.accumulated_pause_time = 0.0
        self.current_alert_text = ""
        
        step = self._get_current_step()
        if step:
            step.time_remaining = step.duration_min * 60
            if step.setpoint_f and step.setpoint_f > 0:
                step.phase = StepPhase.RAMPING
            else:
                step.phase = StepPhase.PROCESSING

        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.stop_event.clear()
            self.worker_thread = threading.Thread(target=self._control_loop, daemon=True)
            self.worker_thread.start()
            
        self._save_state()
    
    def stop(self):
        self.status = SequenceStatus.IDLE
        self.current_alert_text = ""
        self.stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)
        self.relay.turn_off_all_relays()
        self.settings.clear_recovery_state()

    def pause_sequence(self):
        if self.status == SequenceStatus.RUNNING:
            self.status = SequenceStatus.PAUSED
            self.pause_start_time = time.time()
            self.relay.turn_off_all_relays()
            self._save_state()

    def resume_sequence(self):
        if self.status == SequenceStatus.PAUSED:
            pause_duration = time.time() - self.pause_start_time
            self.accumulated_pause_time += pause_duration
            self.status = SequenceStatus.RUNNING
            self._save_state()

    def advance_step(self):
        """Called when user clicks ADVANCE button."""
        
        # 1. Handle "In-Step" Additions (Active Pause)
        # If we are waiting because of an addition, just clear the alert and resume
        if self.status == SequenceStatus.WAITING_FOR_USER and self.current_alert_text != "":
            print("[SEQ] User confirmed addition. Resuming...")
            self.status = SequenceStatus.RUNNING
            self.current_alert_text = ""
            return

        # 2. Handle Actual Step Advance
        self.current_step_index += 1
        self.current_alert_text = ""
        
        if self.current_step_index >= len(self.current_profile.steps):
            self.complete_sequence()
        else:
            self.step_start_time = time.time()
            self.accumulated_pause_time = 0.0
            self.smart_ramp_active = False 
            
            current_step = self._get_current_step()
            if hasattr(current_step, 'reset'): current_step.reset()
            current_step.time_remaining = current_step.duration_min * 60
            
            if current_step.step_type == StepType.DELAYED_START:
                current_step.phase = StepPhase.PROCESSING 
            elif current_step.setpoint_f and current_step.setpoint_f > 0:
                current_step.phase = StepPhase.RAMPING
            else:
                current_step.phase = StepPhase.PROCESSING

            # Manual Steps still pause immediately
            manual_types = [StepType.SG_READING, StepType.LAUTER, StepType.HOPS_ADJUNCTS]
            if current_step.step_type in manual_types:
                 self.status = SequenceStatus.WAITING_FOR_USER
            else:
                 self.status = SequenceStatus.RUNNING
            
            self._save_state()
            
    def complete_sequence(self):
        self.status = SequenceStatus.COMPLETED
        self.relay.turn_off_all_relays()
        self.settings.clear_recovery_state()

    def update(self):
        if self.status == SequenceStatus.RUNNING and (self.worker_thread is None or not self.worker_thread.is_alive()):
             self.stop_event.clear()
             self.worker_thread = threading.Thread(target=self._control_loop, daemon=True)
             self.worker_thread.start()

    def _control_loop(self):
        while not self.stop_event.is_set():
            if self.status == SequenceStatus.RUNNING:
                self._evaluate_current_step()
            elif self.status == SequenceStatus.WAITING_FOR_USER:
                # Active Wait: Keep PID running!
                self._evaluate_holding_pattern()
            
            time.sleep(0.5) 

    def _evaluate_holding_pattern(self):
        step = self._get_current_step()
        if not step: return
        if step.setpoint_f and step.setpoint_f > 0:
             self._logic_pid_hold(step)
        elif step.step_type == StepType.BOIL:
             self._logic_pwm_boil(step)
        else:
             self.relay.turn_off_all_relays()

    def _evaluate_current_step(self):
        step = self._get_current_step()
        if not step: return
        if not hasattr(step, 'phase'): step.phase = StepPhase.PROCESSING

        if step.step_type == StepType.DELAYED_START:
            self._logic_delayed_start(step)
            self._check_step_completion(step)
            return

        if step.phase == StepPhase.RAMPING:
            current_temp = self._read_temp()
            self._logic_pid_hold(step)
            
            if current_temp >= step.setpoint_f:
                # Zero-duration check
                if step.duration_min <= 0:
                    self.relay.turn_off_all_relays()
                    b_str = str(step.timeout_behavior).lower()
                    if "auto" in b_str: self.advance_step()
                    else: self.status = SequenceStatus.WAITING_FOR_USER
                    return
                
                step.phase = StepPhase.PROCESSING
                self.step_start_time = time.time()
                self.accumulated_pause_time = 0.0
                step.time_remaining = step.duration_min * 60
            else:
                return 

        elif step.phase == StepPhase.PROCESSING:
            if step.step_type in [StepType.MASH, StepType.STEP, StepType.MASH_OUT, StepType.LAUTER]:
                self._logic_pid_hold(step)
            elif step.step_type == StepType.BOIL:
                self._logic_pwm_boil(step)
            
            # --- CHECK ADDITIONS ---
            self._check_additions(step)
            self._check_step_completion(step)

    def _check_additions(self, step: BrewStep):
        """Checks if any additions are due based on time remaining."""
        if not step.additions: return
        
        elapsed = time.time() - self.step_start_time - self.accumulated_pause_time
        remaining_sec = (step.duration_min * 60) - elapsed
        remaining_min = remaining_sec / 60.0
        
        for add in step.additions:
            if not add.triggered:
                # Trigger if time is equal or passed (with buffer)
                if remaining_min <= (add.time_point_min + 0.5):
                    print(f"[SEQ] Triggering Addition: {add.name}")
                    add.triggered = True
                    self.current_alert_text = f"ADDITION: {add.name}"
                    self.status = SequenceStatus.WAITING_FOR_USER
                    return

    def _get_current_step(self):
        if self.current_profile and 0 <= self.current_step_index < len(self.current_profile.steps):
            return self.current_profile.steps[self.current_step_index]
        return None

    def _read_temp(self):
        return self.hw.read_temperature()

    def _logic_delayed_start(self, step: BrewStep):
        self._run_pid(step.setpoint_f)
            
    def _logic_pid_hold(self, step: BrewStep):
        current_temp = self._read_temp()
        target = step.setpoint_f
        if target and current_temp < target:
            self.relay.set_relays(True, True, False)
        else:
            self.relay.turn_off_all_relays()

    def _logic_pwm_boil(self, step: BrewStep):
        self.relay.set_relays(True, True, False)
        
    def _run_pid(self, setpoint):
        step_dummy = BrewStep(setpoint_f=setpoint)
        self._logic_pid_hold(step_dummy)
        
    def _check_step_completion(self, step: BrewStep):
        elapsed = time.time() - self.step_start_time - self.accumulated_pause_time
        elapsed_min = elapsed / 60.0
        
        if step.duration_min > 0:
             step.time_remaining = (step.duration_min * 60) - elapsed
        else:
             step.time_remaining = 0
        
        if step.duration_min > 0 and elapsed_min >= step.duration_min:
            self.relay.turn_off_all_relays()
            b_str = str(step.timeout_behavior).lower()
            if "auto" in b_str: self.advance_step()
            else: self.status = SequenceStatus.WAITING_FOR_USER

    def _save_state(self):
        state = {
            "profile_id": self.current_profile.id if self.current_profile else None,
            "step_index": self.current_step_index,
            "status": self.status,
            "start_time": self.step_start_time,
            "accumulated_pause": self.accumulated_pause_time
        }
        self.settings.save_recovery_state(state)

    def _check_recovery(self):
        saved_state = self.settings.get_recovery_state()
        if saved_state and saved_state.get("status") == "Running":
            print("CRASH DETECTED: Resuming Brew Sequence...")
    
    @property
    def current_temp(self): return self._read_temp()
    @property
    def is_heating(self): return False
    
    def get_display_timer(self):
        step = self._get_current_step()
        if not step: return "00:00"
        if hasattr(step, 'phase') and step.phase == StepPhase.RAMPING:
             total_sec = step.duration_min * 60
             m, s = divmod(int(total_sec), 60)
             return f"{m:02d}:{s:02d}"
        if step.duration_min > 0:
            remaining = getattr(step, 'time_remaining', step.duration_min * 60)
            if remaining < 0: remaining = 0
            m, s = divmod(int(remaining), 60)
            return f"{m:02d}:{s:02d}"
        return "00:00"

    def get_status_message(self):
        if self.status == SequenceStatus.IDLE: return "System Idle"
        
        # If there is an alert (Addition), show that!
        if self.current_alert_text:
            return f"⚠ {self.current_alert_text}"

        step = self._get_current_step()
        name = step.name if step else "Unknown"
        extra = ""
        if step and hasattr(step, 'phase') and step.phase == StepPhase.RAMPING:
            extra = " (HEATING)"
        elif self.status == SequenceStatus.WAITING_FOR_USER:
            extra = " (WAITING)"
            
        return f"{self.status.value}: {name}{extra}"
        
    def get_target_temp(self):
        step = self._get_current_step()
        if step: return step.setpoint_f
        return None
        
    def get_upcoming_additions(self):
        step = self._get_current_step()
        if not step or not step.additions: return ""
        for add in step.additions:
            if not add.triggered:
                return f"Next: {add.name} @ {add.time_point_min}m"
        return ""
    
    def get_step_preview_texts(self):
        return ("", "", "")
