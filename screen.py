import sys
import pygame
import json
import os
import time

PI = "-PI" in sys.argv

if PI:
    import RPi.GPIO as GPIO

# ── Config ────────────────────────────────────────────────────────────────────

SWITCH_PINS = {
    17: 10,
    18: 20,
    22: 30,
    23: 50,
    24: 100,
}

MAX_BALLS = 9
HIGH_SCORE_FILE = "highscores.json"
SCREEN_W, SCREEN_H = 800*2, 480*2

# ── Colors ────────────────────────────────────────────────────────────────────

BG          = (15,  15,  20)
SURFACE     = (28,  28,  38)
ACCENT      = (55, 138, 221)    # blue
ACCENT_DIM  = (30,  80, 140)
GOLD        = (186, 117,  23)
WHITE       = (240, 240, 245)
GRAY        = (120, 120, 135)
DARK_GRAY   = (50,  50,  62)
GREEN       = (29, 158, 117)
RED         = (226,  75,  74)

# ── GPIO setup ────────────────────────────────────────────────────────────────

def setup_gpio(callback):
    GPIO.setmode(GPIO.BCM)
    for pin in SWITCH_PINS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(pin, GPIO.FALLING, callback=callback, bouncetime=300)

# ── High score persistence ────────────────────────────────────────────────────

def load_scores():
    if os.path.exists(HIGH_SCORE_FILE):
        with open(HIGH_SCORE_FILE) as f:
            return json.load(f)
    return []

def save_scores(scores):
    with open(HIGH_SCORE_FILE, "w") as f:
        json.dump(scores, f)


# ── Main app ──────────────────────────────────────────────────────────────────

class SkeeBall:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN)
        self.W, self.H = self.screen.get_size()
        pygame.display.set_caption("Skeeball")

        self.font_huge  = pygame.font.SysFont("dejavusans", 180, bold=False)
        self.font_large = pygame.font.SysFont("dejavusans", 90, bold=False)
        self.font_med   = pygame.font.SysFont("dejavusans", 50, bold=False)
        self.font_small = pygame.font.SysFont("dejavusans", 36, bold=False)

        self.clock = pygame.time.Clock()
        self.score = 0
        self.balls_thrown = 0
        self.history = []
        self.high_scores = load_scores()
        self.state = "playing"   # playing | game_over
        self.flash = None        # (points, timestamp)
        self.last_hit = None     # points value of last hit (for lighting up board)

        # GPIO
        if PI:
            try:
                setup_gpio(self._gpio_callback)
                self.gpio_ok = True
            except Exception as e:
                print(f"GPIO not available: {e}")
                self.gpio_ok = False
        else:
            self.gpio_ok = False

        # Thread-safe score queue
        self._pending_points = []

    def _gpio_callback(self, channel):
        pts = SWITCH_PINS.get(channel, 0)
        self._pending_points.append(pts)

    # ── Game logic ────────────────────────────────────────────────────────────

    def add_score(self, pts):
        if self.state != "playing" or self.balls_thrown >= MAX_BALLS:
            return
        self.score += pts
        self.balls_thrown += 1
        self.history.append(pts)
        self.flash = (pts, pygame.time.get_ticks())
        self.last_hit = pts
        if self.balls_thrown >= MAX_BALLS:
            self._end_game()

    def _end_game(self):
        self.state = "game_over"
        # Auto-save score
        self.high_scores.append({"name": "Player", "score": self.score})
        self.high_scores.sort(key=lambda h: h["score"], reverse=True)
        self.high_scores = self.high_scores[:10]
        save_scores(self.high_scores)

    def _reset(self):
        self.score = 0
        self.balls_thrown = 0
        self.history = []
        self.flash = None
        self.last_hit = None
        self.state = "playing"

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw_rounded_rect(self, surf, color, rect, radius=12):
        pygame.draw.rect(surf, color, rect, border_radius=radius)

    def _draw_skeeball_board(self, cx, cy, size):
        """Draw a skeeball target board centered at (cx, cy) with given size."""
        scr = self.screen

        # Ring definitions: (points, radius_ratio, color_dim, color_lit)
        rings = [
            (10, 1.0,   (40, 50, 45),   (60, 180, 100)),    # outer - 10 pts
            (20, 0.75,  (50, 45, 50),   (140, 90, 180)),    # 20 pts
            (30, 0.50,  (50, 50, 60),   (80, 140, 200)),    # 30 pts
            (50, 0.30,  (60, 50, 45),   (200, 150, 60)),    # 50 pts
            (100, 0.15, (70, 45, 45),   (220, 80, 80)),     # center - 100 pts
        ]

        # Draw rings from outer to inner
        for pts, ratio, col_dim, col_lit in rings:
            r = int(size * ratio)
            col = col_lit if self.last_hit == pts else col_dim
            pygame.draw.circle(scr, col, (cx, cy), r)
            # Draw ring border
            pygame.draw.circle(scr, DARK_GRAY, (cx, cy), r, 3)

        # Draw point labels on rings
        label_font = self.font_small
        label_positions = [
            (100, 0.075),   # center
            (50, 0.225),    # 50 ring
            (30, 0.40),     # 30 ring
            (20, 0.625),    # 20 ring
            (10, 0.875),    # 10 ring (outer)
        ]
        for pts, ratio in label_positions:
            label = label_font.render(str(pts), True, WHITE if self.last_hit == pts else GRAY)
            lx = cx - label.get_width() // 2
            ly = cy - int(size * ratio) - label.get_height() // 2
            scr.blit(label, (lx, ly))

    def _draw_playing(self):
        scr = self.screen
        W, H = self.W, self.H

        # Left panel — score
        panel_w = W - 300
        self._draw_rounded_rect(scr, SURFACE, (20, 20, panel_w, H - 40), 16)

        # Score label
        lbl = self.font_small.render("SCORE", True, GRAY)
        scr.blit(lbl, (20 + panel_w // 2 - lbl.get_width() // 2, 60))

        # Score number
        score_surf = self.font_huge.render(str(self.score), True, WHITE)
        scr.blit(score_surf, (20 + panel_w // 2 - score_surf.get_width() // 2, 120))

        # Flash "+pts"
        if self.flash:
            pts, ts = self.flash
            age = pygame.time.get_ticks() - ts
            if age < 1000:
                alpha = max(0, 255 - int(255 * age / 1000))
                fsuf = self.font_large.render(f"+{pts}", True, GREEN)
                fsuf.set_alpha(alpha)
                scr.blit(fsuf, (20 + panel_w // 2 - fsuf.get_width() // 2, 320))

        # Skeeball board graphic
        board_cx = 20 + panel_w // 2
        board_cy = H // 2 + 80
        board_size = min(panel_w - 100, H - 500) // 2
        self._draw_skeeball_board(board_cx, board_cy, board_size)

        # Balls remaining
        ball_y = H - 180
        ball_label = self.font_small.render("BALLS", True, GRAY)
        scr.blit(ball_label, (20 + panel_w // 2 - ball_label.get_width() // 2, ball_y - 50))
        ball_r = 35
        ball_spacing = 20
        total_balls_w = MAX_BALLS * (ball_r * 2) + (MAX_BALLS - 1) * ball_spacing
        bx = 20 + panel_w // 2 - total_balls_w // 2 + ball_r
        balls_remaining = MAX_BALLS - self.balls_thrown
        for i in range(MAX_BALLS):
            col = ACCENT if i < balls_remaining else DARK_GRAY
            pygame.draw.circle(scr, col, (bx + i * (ball_r * 2 + ball_spacing), ball_y + ball_r), ball_r)

        # Right panel — high scores (skinny)
        rw = 260
        rx = W - rw - 20
        self._draw_rounded_rect(scr, SURFACE, (rx, 20, rw, H - 40), 16)

        hs_title = self.font_small.render("HIGH SCORES", True, GRAY)
        scr.blit(hs_title, (rx + rw // 2 - hs_title.get_width() // 2, 50))

        pygame.draw.line(scr, DARK_GRAY, (rx + 16, 100), (rx + rw - 16, 100), 1)

        for i, entry in enumerate(self.high_scores[:7]):
            ey = 120 + i * 70
            rank_col = GOLD if i == 0 else (GRAY if i > 2 else WHITE)
            rank_s = self.font_small.render(f"{i+1}.", True, rank_col)
            score_s = self.font_med.render(str(entry["score"]), True, ACCENT if i == 0 else WHITE)
            scr.blit(rank_s, (rx + 16, ey + 4))
            scr.blit(score_s, (rx + rw - 16 - score_s.get_width(), ey))

        if not self.high_scores:
            empty = self.font_small.render("No scores", True, GRAY)
            scr.blit(empty, (rx + rw // 2 - empty.get_width() // 2, 180))

    def _draw_game_over(self):
        scr = self.screen
        W, H = self.W, self.H

        # Dim overlay
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        scr.blit(overlay, (0, 0))

        # Modal
        mw, mh = 440, 180
        mx, my = W // 2 - mw // 2, H // 2 - mh // 2
        self._draw_rounded_rect(scr, SURFACE, (mx, my, mw, mh), 16)
        pygame.draw.rect(scr, ACCENT_DIM, (mx, my, mw, mh), 2, border_radius=16)

        title = self.font_large.render("Game Over!", True, WHITE)
        scr.blit(title, (mx + mw // 2 - title.get_width() // 2, my + 30))

        sc_text = self.font_med.render(f"Final Score: {self.score}", True, ACCENT)
        scr.blit(sc_text, (mx + mw // 2 - sc_text.get_width() // 2, my + 100))

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(60)

            # Drain GPIO queue
            while self._pending_points:
                self.add_score(self._pending_points.pop(0))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

            self.screen.fill(BG)
            self._draw_playing()
            if self.state == "game_over":
                self._draw_game_over()

            pygame.display.flip()

        if self.gpio_ok:
            GPIO.cleanup()
        pygame.quit()


if __name__ == "__main__":
    SkeeBall().run()
