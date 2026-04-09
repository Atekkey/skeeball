import sys
import pygame
import json
import os
import time

PI = not ("-NOPI" in sys.argv)
EOH = "-EOH" in sys.argv

if PI:
    import RPi.GPIO as GPIO

# ── Config ────────────────────────────────────────────────────────────────────
PIN_TOP_LEFT = 24 # GOOD
PIN_TOP_MID = 12 
PIN_TOP_RIGHT = 27 # GOOD
PIN_BOTTOM_0 = 26 # GOOD
PIN_BOTTOM_1 = 25
PIN_BOTTOM_2 = 17
PIN_BOTTOM_3 = 6 
SWITCH_PINS = { # SCORES
    PIN_TOP_LEFT: 100,
    PIN_TOP_MID: 50,
    PIN_TOP_RIGHT: 100,
    PIN_BOTTOM_0: 10,
    PIN_BOTTOM_1: 20,
    PIN_BOTTOM_2: 30,
    PIN_BOTTOM_3: 40,
}
PIN_RESET = 16 # GOOD

MAX_BALLS = 9
try:
    MAX_BALLS = int(sys.argv[-1])
except (IndexError, ValueError):
    pass

HIGH_SCORE_FILE = "highscores.json" if not EOH else ""
# ── Colors ────────────────────────────────────────────────────────────────────
BG          = (15,  15,  20)
SURFACE     = (28,  28,  38)
SURFACE2     = (28,  28,  38+5)
ACCENT       = (255, 150, 50)
ACCENT_DIM   = (255, 150, 50, 100)
GREEN       = (50,  200, 100)
GOLD        = (186+20, 117+20,  23+20)
SILVER      = (192, 192, 192)
BRONZE      = (175, 107,  30)
WHITE       = (240, 240, 245)
GRAY        = (120, 120, 135)
DARK_GRAY   = (50,  50,  62)
ORANGE      = (255, 150, 50)
BALL_LAB_COL = (69, 91, 195)
# ── GPIO setup ────────────────────────────────────────────────────────────────
def setup_gpio(callback):
    GPIO.setmode(GPIO.BCM)
    for pin in SWITCH_PINS:
        try:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(pin, GPIO.FALLING, callback=callback, bouncetime=300)
        except Exception as e:
            print(f"Error setting up GPIO pin: {pin}")
    try:
        GPIO.setup(PIN_RESET, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(PIN_RESET, GPIO.FALLING, callback=callback, bouncetime=100) # check time later
    except Exception as e:
        print(f"Error setting up GPIO pin: {PIN_RESET}")
# ── High score persistence ────────────────────────────────────────────────────
def load_scores():
    if HIGH_SCORE_FILE == "":
        return []
    if os.path.exists(HIGH_SCORE_FILE):
        with open(HIGH_SCORE_FILE) as f:
            return json.load(f)
    return []
def save_scores(scores):
    if HIGH_SCORE_FILE == "":
        return
    with open(HIGH_SCORE_FILE, "w") as f:
        json.dump(scores, f)

# ── Main app ──────────────────────────────────────────────────────────────────

class SkeeBall:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN)
        self.W, self.H = self.screen.get_size()
        pygame.display.set_caption("Skeeball")
        
        self.font_huge_score  = pygame.font.SysFont("comicsans", 280 + (PI*240), bold=False)
        self.font_huge  = pygame.font.SysFont("comicsans", 180, bold=False)
        self.font_large = pygame.font.SysFont("comicsans", 90, bold=False)
        self.font_med   = pygame.font.SysFont("comicsans", 50, bold=False)
        self.font_small = pygame.font.SysFont("comicsans", 36, bold=False)
        self.font_v_small = pygame.font.SysFont("comicsans", 22, bold=False)

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
        try:
            if self.state == "initials":
                if channel == PIN_RESET:
                    self.ords[self.letter_idx] += 1
                    if self.ords[self.letter_idx] > 90: # Z to A
                        self.ords[self.letter_idx] = 45 # -
                    elif self.ords[self.letter_idx] == 46: # - to A
                        self.ords[self.letter_idx] = 65 # A
                else:
                    self.letter_idx += 1
                    if self.letter_idx >= 3:
                        self._submit_inits()
                        return
            if self.state == "playing":
                if channel != PIN_RESET:
                    pts = SWITCH_PINS.get(channel, 0)
                    self._pending_points.append(pts)
                    return
            if self.state != "initials":
                self._end_game(True)
        except Exception as e:
            print(f"Error in GPIO callback: {e}")

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

    def _end_game(self, reset=False):
        self.state = "game_over"
        if reset:
            self._reset()
            return
        ## END BY 10 balls thrown        
        if EOH:
            return
        self.high_scores.sort(key=lambda h: h["score"], reverse=True)
        tenth_high = (self.high_scores[min(9, len(self.high_scores)-1)])["score"] # 10th highest

        if self.score > tenth_high or len(self.high_scores) < 10:
            self.state = "initials"
        
        # self._reset() # TODO REPLACE

    def _submit_inits(self):
        initials = "".join(chr(o) for o in self.ords)
        self.high_scores.append({"name": initials, "score": self.score})
        self.high_scores.sort(key=lambda h: h["score"], reverse=True)
        self.high_scores = self.high_scores[:10]
        save_scores(self.high_scores)
        self._reset()
        
    def _reset(self):
        self.score = 0
        self.balls_thrown = 0
        self.history = []
        self.flash = None
        self.last_hit = None
        self.letter_idx = 0
        self.state = "playing"
        

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw_rounded_rect(self, surf, color, rect, radius=12):
        pygame.draw.rect(surf, color, rect, border_radius=radius)
    
    def _draw_playing(self):
        scr = self.screen
        W, H = self.W, self.H

        # Left panel — score
        panel_w = W - (310 * (not EOH))
        self._draw_rounded_rect(scr, SURFACE, (20, 20, panel_w, H - 40), 16)

        # Score label
        f = self.font_small if not PI else self.font_large
        lbl = f.render("SCORE", True, GRAY)
        scr.blit(lbl, (20 + panel_w // 2 - lbl.get_width() // 2, 60))

        # Score number
        score_surf = self.font_huge_score.render(str(self.score), True, WHITE)
        scr.blit(score_surf, (20 + panel_w // 2 - score_surf.get_width() // 2, 120))

        # Flash "+pts"
        if self.flash:
            pts, ts = self.flash
            age = pygame.time.get_ticks() - ts
            if age < 1000:
                alpha = max(0, 255 - int(255 * age / 1000))
                fsuf = self.font_huge.render(f"+{pts}", True, GREEN)
                fsuf.set_alpha(alpha)
                scr.blit(fsuf, (20 + panel_w // 2 - fsuf.get_width() // 2, 320 + (PI*100)))
        
        # Balls remaining
        ball_y = H - 220 - 100
        ball_label = self.font_large.render("BALLS", True, BALL_LAB_COL)
        ball_r = 35 if not PI else 60
        ball_y_2 = 2.5 * ball_r + ball_y
        scr.blit(ball_label, (20 + panel_w // 2 - ball_label.get_width() // 2, ball_y - 140))
        
        ball_spacing = 20
        total_balls_w = MAX_BALLS * (ball_r * 2) + (MAX_BALLS - 1) * ball_spacing
        bx = 20 + panel_w // 2 - total_balls_w // 4 + ball_r
        balls_remaining = MAX_BALLS - self.balls_thrown
        diff = (MAX_BALLS % 2) * (ball_r + ball_spacing // 2)
        for i in range(MAX_BALLS):
            col = ACCENT if MAX_BALLS - i - 1 < balls_remaining else DARK_GRAY
            if i % 2 == 0:
                pygame.draw.circle(scr, BALL_LAB_COL, (bx + (i//2) * (ball_r * 2 + ball_spacing), ball_y), ball_r+3 + (PI*10))
                pygame.draw.circle(scr, col, (bx + (i//2) * (ball_r * 2 + ball_spacing), ball_y), ball_r)
            else: 
                pygame.draw.circle(scr, BALL_LAB_COL, (diff + bx + (i//2) * (ball_r * 2 + ball_spacing), ball_y_2), ball_r+3+ (PI*10))
                pygame.draw.circle(scr, col, (diff + bx + (i//2) * (ball_r * 2 + ball_spacing), ball_y_2), ball_r)

        # Right panel — high scores (skinny)
        if not EOH: # IF EOH no high score panel
            rw = 260
            rx = W - rw - 20
            self._draw_rounded_rect(scr, SURFACE2, (rx, 20, rw, H - 40), 16)

            hs_title = self.font_v_small.render("HIGH SCORES", True, GRAY)
            scr.blit(hs_title, (rx + rw // 2 - hs_title.get_width() // 2, 50))

            pygame.draw.line(scr, DARK_GRAY, (rx + 16, 100), (rx + rw - 16, 100), 1)

            for i, entry in enumerate(self.high_scores[:10]):
                ey = 120 + i * 70
                if i == 0:
                    rank_col = GOLD
                elif i == 1:
                    rank_col = SILVER
                elif i == 2:
                    rank_col = BRONZE
                else:
                    rank_col = GRAY
                rank_s = self.font_small.render(str(entry["name"]) + ":", True, rank_col)
                score_s = self.font_med.render(str(entry["score"]), True, rank_col)
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
    
    def _draw_enter_inits(self):
        # Click reset button to cycle letter
        # throw ball in any hole to confirm that letter and move to next

        # Initialize ords and letter_idx only once (on first call)
        if not hasattr(self, 'ords'):
            self.ords = [45, 45, 45]  # ---
            self.letter_idx = 0

        scr = self.screen
        W, H = self.W, self.H

        # Dim overlay
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        scr.blit(overlay, (0, 0))

        # Modal box
        mw, mh = 600, 400
        mx, my = W // 2 - mw // 2, H // 2 - mh // 2
        self._draw_rounded_rect(scr, SURFACE, (mx, my, mw, mh), 16)
        pygame.draw.rect(scr, ACCENT, (mx, my, mw, mh), 3, border_radius=16)

        # "NEW HIGH SCORE!" title
        title = self.font_med.render("NEW HIGH SCORE!", True, GOLD)
        scr.blit(title, (mx + mw // 2 - title.get_width() // 2, my + 30))

        # Score display
        sc_text = self.font_med.render(f"Score: {self.score}", True, WHITE)
        scr.blit(sc_text, (mx + mw // 2 - sc_text.get_width() // 2, my + 110))

        # "Enter Initials" label
        enter_lbl = self.font_small.render("ENTER INITIALS", True, GRAY)
        scr.blit(enter_lbl, (mx + mw // 2 - enter_lbl.get_width() // 2, my + 170))

        # Draw the 3 letter boxes
        box_size = 80
        box_spacing = 30
        total_w = 3 * box_size + 2 * box_spacing
        box_start_x = mx + mw // 2 - total_w // 2
        box_y = my + 220

        for i in range(3):
            bx = box_start_x + i * (box_size + box_spacing)

            # Box background - highlight current letter
            if i == self.letter_idx:
                self._draw_rounded_rect(scr, ACCENT, (bx - 4, box_y - 4, box_size + 8, box_size + 8), 12)
                box_col = SURFACE2
                letter_col = WHITE
            elif i < self.letter_idx:
                box_col = DARK_GRAY
                letter_col = GREEN
            else:
                box_col = DARK_GRAY
                letter_col = GRAY

            self._draw_rounded_rect(scr, box_col, (bx, box_y, box_size, box_size), 10)

            # Draw the letter
            letter = chr(self.ords[i])
            letter_surf = self.font_large.render(letter, True, letter_col)
            lx = bx + box_size // 2 - letter_surf.get_width() // 2
            ly = box_y + box_size // 2 - letter_surf.get_height() // 2
            scr.blit(letter_surf, (lx, ly))

        # Instructions at bottom
        instr1 = self.font_v_small.render("RESET BUTTON = Change Letter", True, GRAY)
        instr2 = self.font_v_small.render("ANY HOLE = Confirm Letter", True, GRAY)
        scr.blit(instr1, (mx + mw // 2 - instr1.get_width() // 2, my + mh - 70))
        scr.blit(instr2, (mx + mw // 2 - instr2.get_width() // 2, my + mh - 40))


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
            if self.state == "initials":
                self._draw_enter_inits()

            pygame.display.flip()

        if self.gpio_ok:
            GPIO.cleanup()
        pygame.quit()


if __name__ == "__main__":
    SkeeBall().run()
