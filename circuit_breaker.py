import time
import logging

logger = logging.getLogger("CircuitBreaker")

class PortfolioCircuitBreaker:
    def __init__(self, max_stops=3, window_sec=1800, cooldown_sec=2700):
        self.max_stops = max_stops          # Max stop-losses allowed
        self.window_sec = window_sec        # 30-minute rolling window
        self.cooldown_sec = cooldown_sec    # 45-minute trading pause
        self.stop_timestamps = []
        self.is_tripped = False
        self.cooldown_until = 0

    def record_stop_loss(self):
        now = time.time()
        self.stop_timestamps.append(now)
        # Prune old timestamps
        self.stop_timestamps = [t for t in self.stop_timestamps if now - t <= self.window_sec]

        if len(self.stop_timestamps) >= self.max_stops:
            self.is_tripped = True
            self.cooldown_until = now + self.cooldown_sec
            logger.critical(
                f"🚨 [PORTFOLIO CIRCUIT BREAKER TRIPPED] {len(self.stop_timestamps)} stop-losses in {self.window_sec/60:.0f}m! "
                f"All new entries PAUSED until {time.strftime('%H:%M:%S', time.localtime(self.cooldown_until))}"
            )

    def can_open_new_position(self) -> tuple[bool, str]:
        now = time.time()
        if self.is_tripped:
            if now >= self.cooldown_until:
                self.is_tripped = False
                self.stop_timestamps.clear()
                logger.info("✅ [CIRCUIT BREAKER RESET] Cooldown period expired. Resuming normal entries.")
                return True, "Breaker reset"
            else:
                remaining_m = (self.cooldown_until - now) / 60.0
                return False, f"Circuit Breaker active ({remaining_m:.1f}m remaining)"
        return True, "Normal operation"
