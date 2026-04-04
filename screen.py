PI = False
import pygame
if PI:
    import RPi.GPIO as GPIO
import json
import os
import time

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
SCREEN_W, SCREEN_H = 800*3, 480*3   # typical Pi touchscreen / HDMI

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

# ── Text input widget ─────────────────────────────────────────────────────────

class TextInput:
    def __init__(self, rect, font):
        self.rect = pygame.Rect(rect)
        self.font = font
        self.text = ""
        self.active = False
        self.cursor_vis = True
        self.cursor_timer = 0

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        if self.active and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key not in (pygame.K_RETURN, pygame.K_ESCAPE):
                if len(self.text) < 16:
                    self.text += event.unicode
        return event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN

    def update(self, dt):
        self.cursor_timer += dt
        if self.cursor_timer > 500:
            self.cursor_vis = not self.cursor_vis
            self.cursor_timer = 0

    def draw(self, surf):
        border_col = ACCENT if self.active else DARK_GRAY
        pygame.draw.rect(surf, SURFACE, self.rect, border_radius=8)
        pygame.draw.rect(surf, border_col, self.rect, 2, border_radius=8)
        display = self.text + ("|" if self.active and self.cursor_vis else "")
        label = self.font.render(display, True, WHITE)
        surf.blit(label, (self.rect.x + 12, self.rect.centery - label.get_height() // 2))


# ── Main app ──────────────────────────────────────────────────────────────────

class SkeeBall:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Skeeball")

        self.font_huge  = pygame.font.SysFont("dejavusans", 96, bold=False)
        self.font_large = pygame.font.SysFont("dejavusans", 48, bold=False)
        self.font_med   = pygame.font.SysFont("dejavusans", 30, bold=False)
        self.font_small = pygame.font.SysFont("dejavusans", 22, bold=False)

        self.clock = pygame.time.Clock()
        self.score = 0
        self.balls_thrown = 0
        self.history = []
        self.high_scores = load_scores()
        self.state = "playing"   # playing | game_over
        self.flash = None        # (points, timestamp)
        self.new_score_rank = None

        self.name_input = TextInput(
            (SCREEN_W // 2 - 180, SCREEN_H // 2 + 20, 360, 48),
            self.font_med
        )
        self.name_input.active = True

        # GPIO — comment out if testing without hardware
        try:
            setup_gpio(self._gpio_callback)
            self.gpio_ok = True
        except Exception as e:
            print(f"GPIO not available: {e}")
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
        if self.balls_thrown >= MAX_BALLS:
            self._end_game()

    def undo(self):
        if self.state != "playing" or not self.history:
            return
        pts = self.history.pop()
        self.score -= pts
        self.balls_thrown -= 1

    def _end_game(self):
        self.state = "game_over"
        rank = sum(1 for h in self.high_scores if h["score"] > self.score)
        self.new_score_rank = rank
        self.name_input.text = ""
        self.name_input.active = True

    def _save_and_reset(self):
        name = self.name_input.text.strip() or "Anonymous"
        self.high_scores.append({"name": name, "score": self.score})
        self.high_scores.sort(key=lambda h: h["score"], reverse=True)
        self.high_scores = self.high_scores[:10]
        save_scores(self.high_scores)
        self._reset()

    def _reset(self):
        self.score = 0
        self.balls_thrown = 0
        self.history = []
        self.flash = None
        self.state = "playing"
        self.new_score_rank = None
        self.name_input.text = ""

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw_rounded_rect(self, surf, color, rect, radius=12):
        pygame.draw.rect(surf, color, rect, border_radius=radius)

    def _draw_playing(self):
        scr = self.screen
        W, H = SCREEN_W, SCREEN_H

        # Left panel — score
        panel_w = 380
        self._draw_rounded_rect(scr, SURFACE, (20, 20, panel_w, H - 40), 16)

        # Score label
        lbl = self.font_small.render("SCORE", True, GRAY)
        scr.blit(lbl, (20 + panel_w // 2 - lbl.get_width() // 2, 50))

        # Score number
        score_surf = self.font_huge.render(str(self.score), True, WHITE)
        scr.blit(score_surf, (20 + panel_w // 2 - score_surf.get_width() // 2, 80))

        # Flash "+pts"
        if self.flash:
            pts, ts = self.flash
            age = pygame.time.get_ticks() - ts
            if age < 1000:
                alpha = max(0, 255 - int(255 * age / 1000))
                fsuf = self.font_large.render(f"+{pts}", True, GREEN)
                fsuf.set_alpha(alpha)
                scr.blit(fsuf, (20 + panel_w // 2 - fsuf.get_width() // 2, 190))

        # Balls remaining
        ball_y = 270
        ball_label = self.font_small.render("BALLS", True, GRAY)
        scr.blit(ball_label, (20 + panel_w // 2 - ball_label.get_width() // 2, ball_y - 28))
        ball_r = 14
        total_balls_w = MAX_BALLS * (ball_r * 2 + 6) - 6
        bx = 20 + panel_w // 2 - total_balls_w // 2 + ball_r
        for i in range(MAX_BALLS):
            col = ACCENT if i < self.balls_thrown else DARK_GRAY
            pygame.draw.circle(scr, col, (bx + i * (ball_r * 2 + 6), ball_y + ball_r), ball_r)

        # Buttons: Undo / New Game
        btn_y = H - 40 - 60
        btn_w = (panel_w - 36) // 2
        undo_rect = pygame.Rect(32, btn_y, btn_w, 48)
        new_rect  = pygame.Rect(32 + btn_w + 12, btn_y, btn_w, 48)
        self._draw_rounded_rect(scr, DARK_GRAY, undo_rect, 10)
        self._draw_rounded_rect(scr, DARK_GRAY, new_rect, 10)
        u = self.font_small.render("Undo", True, GRAY)
        n = self.font_small.render("New Game", True, GRAY)
        scr.blit(u, undo_rect.move(undo_rect.w // 2 - u.get_width() // 2, 14))
        scr.blit(n, new_rect.move(new_rect.w // 2 - n.get_width() // 2, 14))
        self._undo_rect = undo_rect
        self._new_rect = new_rect

        # Right panel — high scores
        rx = panel_w + 40
        rw = W - rx - 20
        self._draw_rounded_rect(scr, SURFACE, (rx, 20, rw, H - 40), 16)

        hs_title = self.font_small.render("HIGH SCORES", True, GRAY)
        scr.blit(hs_title, (rx + rw // 2 - hs_title.get_width() // 2, 38))

        pygame.draw.line(scr, DARK_GRAY, (rx + 16, 70), (rx + rw - 16, 70), 1)

        for i, entry in enumerate(self.high_scores[:7]):
            ey = 84 + i * 48
            rank_col = GOLD if i == 0 else (GRAY if i > 2 else WHITE)
            rank_s = self.font_small.render(f"{i+1}", True, rank_col)
            name_s = self.font_med.render(entry["name"][:14], True, WHITE)
            score_s = self.font_med.render(str(entry["score"]), True, ACCENT if i == 0 else WHITE)
            scr.blit(rank_s, (rx + 16, ey + 4))
            scr.blit(name_s, (rx + 42, ey))
            scr.blit(score_s, (rx + rw - 16 - score_s.get_width(), ey))

        if not self.high_scores:
            empty = self.font_small.render("No scores yet", True, GRAY)
            scr.blit(empty, (rx + rw // 2 - empty.get_width() // 2, 120))

    def _draw_game_over(self):
        scr = self.screen
        W, H = SCREEN_W, SCREEN_H

        # Dim overlay
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        scr.blit(overlay, (0, 0))

        # Modal
        mw, mh = 440, 280
        mx, my = W // 2 - mw // 2, H // 2 - mh // 2
        self._draw_rounded_rect(scr, SURFACE, (mx, my, mw, mh), 16)
        pygame.draw.rect(scr, ACCENT_DIM, (mx, my, mw, mh), 2, border_radius=16)

        title = self.font_large.render("Game Over!", True, WHITE)
        scr.blit(title, (mx + mw // 2 - title.get_width() // 2, my + 20))

        sc_text = self.font_med.render(f"Your score: {self.score}", True, ACCENT)
        scr.blit(sc_text, (mx + mw // 2 - sc_text.get_width() // 2, my + 80))

        prompt = self.font_small.render("Enter your name:", True, GRAY)
        scr.blit(prompt, (mx + mw // 2 - prompt.get_width() // 2, my + 120))

        self.name_input.draw(scr)

        # Save button
        save_rect = pygame.Rect(mx + mw // 2 - 80, my + mh - 60, 160, 42)
        self._draw_rounded_rect(scr, ACCENT, save_rect, 10)
        save_lbl = self.font_small.render("Save Score", True, WHITE)
        scr.blit(save_lbl, save_rect.move(save_rect.w // 2 - save_lbl.get_width() // 2, 10))
        self._save_rect = save_rect

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

                if self.state == "playing":
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if hasattr(self, "_undo_rect") and self._undo_rect.collidepoint(event.pos):
                            self.undo()
                        elif hasattr(self, "_new_rect") and self._new_rect.collidepoint(event.pos):
                            self._reset()

                    # Keyboard shortcuts for testing without hardware
                    if event.type == pygame.KEYDOWN:
                        key_map = {
                            pygame.K_1: 10, pygame.K_2: 20, pygame.K_3: 30,
                            pygame.K_4: 50, pygame.K_5: 100
                        }
                        if event.key in key_map:
                            self.add_score(key_map[event.key])

                elif self.state == "game_over":
                    submitted = self.name_input.handle_event(event)
                    if submitted:
                        self._save_and_reset()
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if hasattr(self, "_save_rect") and self._save_rect.collidepoint(event.pos):
                            self._save_and_reset()

            self.name_input.update(dt)

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