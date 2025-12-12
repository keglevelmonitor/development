"""
src/sequence_manager.py
"""
import time
import threading
from datetime import datetime, timedelta
from enum import Enum
from profile_data import BrewProfile, BrewStep, StepType, TimeoutBehavior
from brew_types import StepPhase # <--- NEW IMPORT

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
        self.hw = hardware_interface # <--- NEW: Hardware Interface
        
        # State Variables
        self.current_profile: BrewProfile = None
        self.current_step_index: int = -1
        self.status: SequenceStatus = SequenceStatus.IDLE
        
        # Timing Variables
        self.step_start_time: float = 0.0
        self.pause_start_time: float = 0.0
        self.accumulated_pause_time: float = 0.0
        
        # Smart Ramp Specifics
        self.smart_ramp_active: bool = False
        self.smart_ramp_fire_time: float = 0.0
        
        # Threading for the "Tick" loop
        self.stop_event = threading.Event()
        self.worker_thread = None

        # Load recovery data on boot
        self._check_recovery()

    # --- PUBLIC CONTROL METHODS ---

    def load_profile(self, profile: BrewProfile):
        """Loads a profile and resets state to beginning."""
        self.stop() # Safety reset
        self.current_profile = profile
        self.current_step_index = 0
        self.status = SequenceStatus.IDLE
        
        # Reset step phases
        for s in self.current_profile.steps:
            if hasattr(s, 'reset'): s.reset()
            else: 
                # Backwards compatibility if using old profile objects
                s.phase = StepPhase.PENDING 
        
        self._save_state() # Persist "Loaded but Idle"

    def start_sequence(self):
        """Begins execution of the currently loaded step."""
        if not self.current_profile: return
        
        self.status = SequenceStatus.RUNNING
        self.step_start_time = time.time()
        self.accumulated_pause_time = 0.0
        
        # Initialize Phase for the first step
        step = self._get_current_step()
        if step:
            # If step has a temperature target, we start in RAMPING
            if step.setpoint_f and step.setpoint_f > 0:
                step.phase = StepPhase.RAMPING
            else:
                step.phase = StepPhase.PROCESSING

        # Start the background tick loop
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.stop_event.clear()
            self.worker_thread = threading.Thread(target=self._control_loop, daemon=True)
            self.worker_thread.start()
            
        self._save_state()
    
    def stop(self):
        """Stops execution and resets state."""
        self.status = SequenceStatus.IDLE
        self.stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)
        self.relay.turn_off_all_relays()
        self.settings.clear_recovery_state()

    def pause_sequence(self):
        """Safely turns off heaters but keeps place in the sequence."""
        if self.status == SequenceStatus.RUNNING:
            self.status = SequenceStatus.PAUSED
            self.pause_start_time = time.time()
            self.relay.turn_off_all_relays() # SAFETY FIRST
            self._save_state()

    def resume_sequence(self):
        if self.status == SequenceStatus.PAUSED:
            # Calculate how long we were paused so the timer doesn't "jump"
            pause_duration = time.time() - self.pause_start_time
            self.accumulated_pause_time += pause_duration
            
            self.status = SequenceStatus.RUNNING
            self._save_state()

    def advance_step(self):
        """Manually forced or Auto-triggered move to next step."""
        self.current_step_index += 1
        
        if self.current_step_index >= len(self.current_profile.steps):
            self.complete_sequence()
        else:
            # Reset timer variables for the new step
            self.step_start_time = time.time()
            self.accumulated_pause_time = 0.0
            self.smart_ramp_active = False 
            
            # Setup the new step's phase
            current_step = self._get_current_step()
            if hasattr(current_step, 'reset'): 
                current_step.reset()
            
            # Determine initial phase
            if current_step.step_type == StepType.DELAYED_START:
                current_step.phase = StepPhase.PROCESSING # Logic handles wait
            elif current_step.setpoint_f and current_step.setpoint_f > 0:
                current_step.phase = StepPhase.RAMPING
            else:
                current_step.phase = StepPhase.PROCESSING

            # Check if new step is an Activity (User Input)
            if current_step.step_type in [StepType.SG_READING, StepType.LAUTER, StepType.HOPS_ADJUNCTS]:
                 self.status = SequenceStatus.WAITING_FOR_USER
            else:
                 self.status = SequenceStatus.RUNNING
            
            self._save_state()
            
    def complete_sequence(self):
        self.status = SequenceStatus.COMPLETED
        self.relay.turn_off_all_relays()
        self.settings.clear_recovery_state()

    # --- THE "HEARTBEAT" ---

    def _control_loop(self):
        """Runs 1-4 times per second to evaluate logic."""
        while not self.stop_event.is_set():
            if self.status == SequenceStatus.RUNNING:
                self._evaluate_current_step()
            elif self.status == SequenceStatus.PAUSED:
                pass # Do nothing, relays are already killed in pause_sequence()
            
            # Faster Tick for UI responsiveness
            time.sleep(0.5) 

    def _evaluate_current_step(self):
        step = self._get_current_step()
        if not step: return
        
        # Ensure phase is initialized if something went wrong
        if not hasattr(step, 'phase'): step.phase = StepPhase.PROCESSING

        # --- 1. HANDLE DELAYED START (SMART RAMP) ---
        if step.step_type == StepType.DELAYED_START:
            self._logic_delayed_start(step)
            self._check_step_completion(step)
            return

        # --- 2. HANDLE RAMPING (Wait for Temp) ---
        if step.phase == StepPhase.RAMPING:
            current_temp = self._read_temp()
            
            # Run Heaters
            self._logic_pid_hold(step)
            
            # Check for Transition
            # Note: Add a small buffer? (e.g. >= setpoint - 0.5)
            if current_temp >= step.setpoint_f:
                print(f"[SEQ] Target {step.setpoint_f}F reached. Starting Timer.")
                step.phase = StepPhase.PROCESSING
                # RESET TIMER SO IT STARTS NOW
                self.step_start_time = time.time()
                self.accumulated_pause_time = 0.0
            else:
                # Still heating. Timer is effectively paused.
                return 

        # --- 3. HANDLE PROCESSING (Timer Running) ---
        elif step.phase == StepPhase.PROCESSING:
            # Run Logic based on type
            if step.step_type in [StepType.MASH, StepType.STEP, StepType.MASH_OUT, StepType.LAUTER]:
                self._logic_pid_hold(step)
            elif step.step_type == StepType.BOIL:
                self._logic_pwm_boil(step)
            
            # Check Timeouts
            self._check_step_completion(step)
        
    def _get_current_step(self):
        if self.current_profile and 0 <= self.current_step_index < len(self.current_profile.steps):
            return self.current_profile.steps[self.current_step_index]
        return None

    # --- LOGIC HANDLERS ---
    
    def _read_temp(self):
        """
        UPDATED: Delegates to the Hardware Interface.
        This allows the Slider in Dev Mode to override the real sensor.
        """
        return self.hw.read_temperature()

    def _logic_delayed_start(self, step: BrewStep):
        """
        Handles the 'Ready By' logic (Formerly Smart Ramp).
        """
        if step.target_completion_time:
            # 1. Parse Target Time
            try:
                target_dt = datetime.fromisoformat(step.target_completion_time)
            except ValueError:
                self._run_pid(step.setpoint_f)
                return
                
            now = datetime.now()
            
            if now >= target_dt:
                # Late? Just hold.
                self._run_pid(step.setpoint_f)
                return

            # 2. Calculate Heat Time
            current_temp = self._read_temp()
            target_temp = step.setpoint_f if step.setpoint_f is not None else current_temp
            temp_diff = target_temp - current_temp
            
            degrees_per_minute = self.settings.get("system_settings", "heating_rate_f_min", 1.5) 
            if degrees_per_minute <= 0: degrees_per_minute = 1.5 
            
            minutes_needed = temp_diff / degrees_per_minute
            
            # 3. Calculate "Fire Time"
            fire_dt = target_dt - timedelta(minutes=minutes_needed)
            
            if now >= fire_dt:
                self.smart_ramp_active = True
                self._run_pid(step.setpoint_f)
            else:
                self.relay.turn_off_all_relays()
        else:
            # Standard Ramp if no time set
            self._run_pid(step.setpoint_f)
            
    def _logic_pid_hold(self, step: BrewStep):
        # Simple Placeholder for PID logic
        current_temp = self._read_temp()
        target = step.setpoint_f
        
        # Simple Bang-Bang for testing (Replace with PID later)
        if target and current_temp < target:
            # Heat ON (Both elements for now, or just one if maintaining)
            self.relay.set_relays(True, True, False)
        else:
            self.relay.turn_off_all_relays()

    def _logic_pwm_boil(self, step: BrewStep):
        """
        Runs the heater on a Duty Cycle.
        """
        # Placeholder: Just ON for now
        self.relay.set_relays(True, True, False)
        
    def _run_pid(self, setpoint):
        # Reuse logic from hold
        step_dummy = BrewStep(setpoint_f=setpoint)
        self._logic_pid_hold(step_dummy)
        
    def _check_step_completion(self, step: BrewStep):
        # Calculate Elapsed Time
        # Note: In RAMPING phase, this function isn't called, so this is safe for PROCESSING
        elapsed = time.time() - self.step_start_time - self.accumulated_pause_time
        elapsed_min = elapsed / 60.0
        
        # Update the step object so UI can read it
        if step.duration_min > 0:
             step.time_remaining = (step.duration_min * 60) - elapsed
        else:
             step.time_remaining = 0
        
        # Check against Duration
        if step.duration_min > 0 and elapsed_min >= step.duration_min:
            if step.timeout_behavior == TimeoutBehavior.AUTO_ADVANCE:
                self.advance_step()
            elif step.timeout_behavior == TimeoutBehavior.MANUAL_ADVANCE:
                self.status = SequenceStatus.WAITING_FOR_USER
                # Hold Temp while waiting
                if step.step_type in [StepType.MASH, StepType.STEP]:
                    self._logic_pid_hold(step)
                else:
                    self.relay.turn_off_all_relays()

    # --- RECOVERY ---
    
    def _save_state(self):
        """Saves critical indices to SettingsManager for crash recovery."""
        state = {
            "profile_id": self.current_profile.id if self.current_profile else None,
            "step_index": self.current_step_index,
            "status": self.status,
            "start_time": self.step_start_time,
            "accumulated_pause": self.accumulated_pause_time
        }
        self.settings.save_recovery_state(state)

    def _check_recovery(self):
        """Called on __init__ to see if we crashed while running."""
        saved_state = self.settings.get_recovery_state()
        
        if saved_state and saved_state.get("status") == "Running":
            print("CRASH DETECTED: Resuming Brew Sequence...")
            # (In a full implementation, reload logic goes here)
    
    # --- UI HELPERS ---
    
    @property
    def current_temp(self):
        return self._read_temp()
        
    @property
    def is_heating(self):
        # TODO: Return actual relay state
        return False
        
    def get_display_timer(self):
        """Returns MM:SS formatted string"""
        step = self._get_current_step()
        if not step: return "00:00"

        # If we are waiting for temp, show "HEATING" or similar?
        # Or just show full time remaining.
        if hasattr(step, 'phase') and step.phase == StepPhase.RAMPING:
            # Return full duration while heating
             total_sec = step.duration_min * 60
             m, s = divmod(int(total_sec), 60)
             return f"{m:02d}:{s:02d}"

        # Standard Processing Timer
        if step.duration_min > 0:
            remaining = step.time_remaining # Calculated in loop
            if remaining < 0: remaining = 0
            m, s = divmod(int(remaining), 60)
            return f"{m:02d}:{s:02d}"
        return "00:00"

    def get_status_message(self):
        if self.status == SequenceStatus.IDLE: return "System Idle"
        step = self._get_current_step()
        name = step.name if step else "Unknown"
        
        # Add Ramping info
        extra = ""
        if step and hasattr(step, 'phase') and step.phase == StepPhase.RAMPING:
            extra = " (HEATING)"
            
        return f"{self.status.value}: {name}{extra}"
        
    def get_target_temp(self):
        step = self._get_current_step()
        if step: return step.setpoint_f
        return None
        
    def get_step_preview_texts(self):
        if not self.current_profile: return ("", "", "")
        
        idx = self.current_step_index
        steps = self.current_profile.steps
        
        prev_txt = steps[idx-1].name if idx > 0 else ""
        curr_txt = steps[idx].name if 0 <= idx < len(steps) else ""
        
        # Add details to current text
        if 0 <= idx < len(steps):
            s = steps[idx]
            curr_txt += f"\n{s.step_type.value}"
            if s.duration_min > 0: curr_txt += f" ({s.duration_min}m)"
        
        next_txt = steps[idx+1].name if idx < len(steps)-1 else "End"
        
        return (prev_txt, curr_txt, next_txt)
