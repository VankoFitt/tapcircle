import json
import random
import sys
from pathlib import Path

import pygame

pygame.init()
pygame.mixer.init()


def get_asset_dir():
    """Return the folder to look for bundled assets in.

    When frozen by PyInstaller, files bundled via --add-data are extracted
    to a temp folder exposed as sys._MEIPASS - not the exe's own folder.
    On Android (via Buildozer/python-for-android) this is simply the app's
    own private, writable folder, so the same logic works unchanged.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


ASSET_DIR = get_asset_dir()
if getattr(sys, "frozen", False):
    SAVE_FILE = Path(sys.executable).with_name("tap_circle_save.json")
else:
    SAVE_FILE = Path(__file__).with_name("tap_circle_save.json")

WIDTH = 360
HEIGHT = 640

# Each stop is (points_at_which_this_is_the_pure_layer, fallback_top_color,
# fallback_bottom_color, name, image_filename). The fallback colors are only
# used if the matching image file can't be found/loaded, so the game still
# runs even without the art assets. Images are cross-faded continuously
# between neighboring stops so the background never snaps abruptly from one
# layer to the next.
SKY_LAYERS = [
    (25, (135, 206, 250), (255, 241, 194), "Surface", "Surface.png"),
    (50, (100, 170, 235), (200, 224, 245), "Clouds", "Cloud.png"),
    (75, (58, 110, 190), (120, 150, 210), "Blue", "Blue.png"),
    (100, (25, 45, 90), (55, 65, 120), "Orbit", "Orbit1.png"),
]


def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def load_background_images():
    """Load each sky-layer image, scaled to fill the game window.

    Returns a dict of {name: pygame.Surface}. If a file is missing or fails
    to load, that layer falls back to a plain gradient built from its stop
    colors, so the game still runs before all the art is in place.
    """
    images = {}
    for _points, top_color, bottom_color, name, filename in SKY_LAYERS:
        path = ASSET_DIR / filename
        surface = None
        if path.exists():
            try:
                surface = pygame.image.load(str(path)).convert()
                surface = pygame.transform.smoothscale(surface, (WIDTH, HEIGHT))
            except Exception:
                surface = None

        if surface is None:
            print(f"[tap_circle] background image not found, using fallback color: {filename}")
            surface = pygame.Surface((WIDTH, HEIGHT))
            for y in range(HEIGHT):
                t = y / HEIGHT
                r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
                g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
                b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
                pygame.draw.line(surface, (r, g, b), (0, y), (WIDTH, y))

        images[name] = surface

    return images


def load_sound(*filenames):
    """Try a few filename variants and return the first Sound that loads."""
    for name in filenames:
        path = ASSET_DIR / name
        if path.exists():
            try:
                return pygame.mixer.Sound(str(path))
            except pygame.error:
                pass
    return None


JUMP_SOUND = load_sound("jump.mp3", "jump.MP3", "jump.wav")
WALL_PASS_SOUND = load_sound("wall_pass.mp3", "wall_pass.wav", "pass.mp3", "pass.wav")
CRASH_SOUND = load_sound("crash.mp3", "crash.wav", "hit.mp3", "hit.wav")
GAMEOVER_SOUND = load_sound("gameover.mp3", "gameover.wav")
MUSIC_PATH = None
for candidate in ("music.mp3", "music.MP3", "music.wav"):
    if (ASSET_DIR / candidate).exists():
        MUSIC_PATH = ASSET_DIR / candidate
        break

print(f"[tap_circle] looking for assets in: {ASSET_DIR}")
print(f"[tap_circle] jump sound loaded: {JUMP_SOUND is not None}")
print(f"[tap_circle] wall_pass sound loaded: {WALL_PASS_SOUND is not None}")
print(f"[tap_circle] crash sound loaded: {CRASH_SOUND is not None}")
print(f"[tap_circle] gameover sound loaded: {GAMEOVER_SOUND is not None}")
print(f"[tap_circle] background music found: {MUSIC_PATH is not None}")


class TapCircleGame:
    def __init__(self):
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Tap Circle")
        self.clock = pygame.time.Clock()

        self.font_score = pygame.font.SysFont("Arial", 22, bold=True)
        self.font_best = pygame.font.SysFont("Arial", 14)
        self.font_label = pygame.font.SysFont("Arial", 12)
        self.font_label_italic = pygame.font.SysFont("Arial", 12, italic=True)
        self.font_gear = pygame.font.SysFont("Arial", 16)
        self.font_panel_title = pygame.font.SysFont("Arial", 18, bold=True)
        self.font_close = pygame.font.SysFont("Arial", 12, bold=True)
        self.font_milestone = pygame.font.SysFont("Arial", 12, bold=True)
        self.font_menu_title = pygame.font.SysFont("Arial", 34, bold=True)
        self.font_menu_score = pygame.font.SysFont("Arial", 20, bold=True)
        self.font_menu_sub = pygame.font.SysFont("Arial", 14)
        self.font_menu_big_title = pygame.font.SysFont("Arial", 30, bold=True)

        self.gravity = 0.70
        self.jump_power = -10
        self.start_wall_speed = 2.15
        self.max_wall_speed = 10.0
        self.wall_speed_growth = 0.100
        self.wall_speed = self.start_wall_speed
        self.wall_gap = 150
        self.wall_distance = 200
        self.wall_thickness = 15
        self.start_gap_side_speed = 1.25
        self.max_gap_side_speed = 2.8
        self.gap_side_speed_growth = 0.009
        self.gap_side_speed = self.start_gap_side_speed
        self.camera_top_line = 170
        self.seconds_per_frame = 1 / 60

        save_data = self.load_save_data()
        self.best_score = int(save_data.get("best_score", 0))
        self.music_volume = float(save_data.get("music_volume", 0.5))
        self.sfx_volume = float(save_data.get("sfx_volume", 0.7))

        self.running = False
        self.has_played = False
        self.app_running = True

        # Settings UI geometry
        self.gear_x, self.gear_y, self.gear_r = WIDTH - 30, 30, 16
        self.panel = {"x0": 40, "y0": 190, "x1": 320, "y1": 420}
        self.close_x, self.close_y = self.panel["x1"] - 20, self.panel["y0"] + 20
        self.music_slider = {"x0": 130, "x1": 300, "y": 280}
        self.sfx_slider = {"x0": 130, "x1": 300, "y": 340}
        self.settings_open = False
        self.active_slider = None

        self.background_images = load_background_images()
        self._bg_surface_cache = {}
        self.current_bg_surface = None

        self.reset_game()
        self.start_music()

    # ------------------------------------------------------------------
    # Setup / reset
    # ------------------------------------------------------------------
    def reset_game(self):
        self.player_x = 180
        self.player_y = 500
        self.player_radius = 17
        self.player_velocity_y = 0
        self.camera_y = 0
        self.points = 0
        self.play_time = 0
        self.wall_speed = self.start_wall_speed
        self.gap_side_speed = self.start_gap_side_speed
        self.walls = []
        self.particles = []
        self.jump_trails = []
        self.jump_trail_timer = 0
        self.milestone_effects = []
        self.record_effects = []
        self.new_record_triggered = False

        for index in range(4):
            self.add_wall(-80 - index * self.wall_distance)

    def add_wall(self, y):
        padding = 46
        gap_left = random.randint(padding, WIDTH - self.wall_gap - padding)
        gap_direction = random.choice([-1, 1])
        self.walls.append(
            {
                "y": y,
                "gap_left": gap_left,
                "gap_direction": gap_direction,
                "counted": False,
            }
        )

    def start_game(self):
        self.reset_game()
        self.running = True
        self.has_played = True

    def end_game(self):
        self.running = False
        if self.points > self.best_score:
            self.best_score = self.points
        self.save_progress()
        self.play_gameover_sound()

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.app_running = False

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.handle_click(event.pos[0], event.pos[1])

            elif event.type == pygame.MOUSEMOTION:
                if event.buttons[0]:
                    self.handle_drag(event.pos[0], event.pos[1])

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.handle_release()

            elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                self.handle_click(*pygame.mouse.get_pos())

            # Touch events (Android) report normalized 0..1 coordinates.
            elif event.type == pygame.FINGERDOWN:
                self.handle_click(event.x * WIDTH, event.y * HEIGHT)
            elif event.type == pygame.FINGERMOTION:
                self.handle_drag(event.x * WIDTH, event.y * HEIGHT)
            elif event.type == pygame.FINGERUP:
                self.handle_release()

    def handle_click(self, x, y):
        if self.point_in_circle(x, y, self.gear_x, self.gear_y, self.gear_r):
            self.settings_open = not self.settings_open
            self.active_slider = None
            return

        if self.settings_open:
            self.handle_settings_click(x, y)
            return

        if not self.running:
            self.start_game()
            return

        self.player_velocity_y = self.jump_power
        self.play_jump_sound()

    def handle_drag(self, x, y):
        if not self.settings_open or self.active_slider is None:
            return
        self.update_slider(self.active_slider, x)

    def handle_release(self):
        self.active_slider = None

    def handle_settings_click(self, x, y):
        if self.point_in_circle(x, y, self.close_x, self.close_y, 14):
            self.settings_open = False
            return

        if self.point_near_slider(x, y, self.music_slider):
            self.active_slider = "music"
            self.update_slider("music", x)
            return

        if self.point_near_slider(x, y, self.sfx_slider):
            self.active_slider = "sfx"
            self.update_slider("sfx", x)
            return

    def point_near_slider(self, x, y, track):
        return (
            track["y"] - 14 <= y <= track["y"] + 14
            and track["x0"] - 12 <= x <= track["x1"] + 12
        )

    def point_in_circle(self, x, y, cx, cy, r):
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r

    def update_slider(self, name, x):
        track = self.music_slider if name == "music" else self.sfx_slider
        ratio = (x - track["x0"]) / (track["x1"] - track["x0"])
        ratio = max(0.0, min(1.0, ratio))

        if name == "music":
            self.music_volume = ratio
            pygame.mixer.music.set_volume(ratio)
        else:
            self.sfx_volume = ratio

        self.save_progress()

    # ------------------------------------------------------------------
    # Update loop
    # ------------------------------------------------------------------
    def update(self):
        if not self.running or self.settings_open:
            return

        self.player_velocity_y += self.gravity
        self.player_y += self.player_velocity_y
        self.play_time += self.seconds_per_frame
        self.update_difficulty()
        self.update_camera()
        self.create_continuous_jump_trail()

        previous_points = self.points

        for wall in self.walls:
            wall["gap_left"] += self.gap_side_speed * wall["gap_direction"]

            if wall["gap_left"] < 0:
                wall["gap_left"] = 0
                wall["gap_direction"] = 1

            if wall["gap_left"] + self.wall_gap > WIDTH:
                wall["gap_left"] = WIDTH - self.wall_gap
                wall["gap_direction"] = -1

            if not wall["counted"] and wall["y"] > self.player_y:
                wall["counted"] = True
                self.points += 1
                self.create_paint_splash(wall)
                self.play_wall_pass_sound()

        if self.points != previous_points:
            self.check_milestones()

        self.update_particles()
        self.update_jump_trails()
        self.update_effects()

        if self.walls[0]["y"] - self.camera_y > HEIGHT + self.wall_thickness:
            self.walls.pop(0)
            last_wall = self.walls[-1]
            self.add_wall(last_wall["y"] - self.wall_distance)

        if self.player_y - self.camera_y + self.player_radius > HEIGHT:
            self.end_game()

        for wall in self.walls:
            if self.circle_hits_wall(wall):
                self.play_crash_sound()
                self.end_game()
                break

    def update_difficulty(self):
        self.wall_speed = min(
            self.start_wall_speed + self.play_time * self.wall_speed_growth,
            self.max_wall_speed,
        )
        self.gap_side_speed = min(
            self.start_gap_side_speed + self.play_time * self.gap_side_speed_growth,
            self.max_gap_side_speed,
        )

    def update_camera(self):
        """The world (walls, particles, trails) stays completely still.

        Only the camera moves, and only upward as the player climbs higher
        than the line it currently shows -- and it eases toward that target
        gradually instead of snapping, so it feels like it's 'catching up'.
        """
        target_camera_y = self.player_y - self.camera_top_line

        if target_camera_y >= self.camera_y:
            return

        catch_up_rate = min(0.9, 0.05 * (self.wall_speed / self.start_wall_speed))
        self.camera_y += (target_camera_y - self.camera_y) * catch_up_rate

    def check_milestones(self):
        if self.points > 0 and self.points % 10 == 0:
            self.milestone_effects.append({"life": 55, "max_life": 55, "points": self.points})

        if self.points > self.best_score and not self.new_record_triggered:
            self.new_record_triggered = True
            self.best_score = self.points
            self.record_effects.append({"life": 80, "max_life": 80})

    def update_effects(self):
        for effect in self.milestone_effects:
            effect["life"] -= 1
        self.milestone_effects = [e for e in self.milestone_effects if e["life"] > 0]

        for effect in self.record_effects:
            effect["life"] -= 1
        self.record_effects = [e for e in self.record_effects if e["life"] > 0]

    def create_paint_splash(self, wall):
        splash_x = wall["gap_left"] + self.wall_gap / 2
        splash_y = wall["y"] + self.wall_thickness / 2

        for _ in range(22):
            self.particles.append(
                {
                    "x": splash_x + random.randint(-16, 16),
                    "y": splash_y + random.randint(-10, 10),
                    "velocity_x": random.uniform(-3.2, 3.2),
                    "velocity_y": random.uniform(-3.5, 2.2),
                    "size": random.randint(3, 8),
                    "life": random.randint(18, 34),
                    "color": random.choice(["#39b98f", "#7ee0b8", "#f6f1e8"]),
                }
            )

    def create_continuous_jump_trail(self):
        if self.player_velocity_y >= 0:
            self.jump_trail_timer = 0
            return

        self.jump_trail_timer += 1

        if self.jump_trail_timer % 2 != 0:
            return

        self.jump_trails.append(
            {
                "x": self.player_x + random.randint(-3, 3),
                "y": self.player_y + self.player_radius + random.randint(1, 8),
                "length": random.randint(30, 44),
                "life": 18,
                "color": random.choice(["#fff4bd", "#f7c948", "#f08a4b"]),
            }
        )

    def update_particles(self):
        for particle in self.particles:
            particle["x"] += particle["velocity_x"]
            particle["y"] += particle["velocity_y"]
            particle["velocity_y"] += 0.12
            particle["life"] -= 1

        self.particles = [particle for particle in self.particles if particle["life"] > 0]

    def update_jump_trails(self):
        for trail in self.jump_trails:
            trail["y"] += 2.5
            trail["life"] -= 1

        self.jump_trails = [trail for trail in self.jump_trails if trail["life"] > 0]

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------
    def start_music(self):
        if MUSIC_PATH is None:
            return
        try:
            pygame.mixer.music.load(str(MUSIC_PATH))
            pygame.mixer.music.set_volume(self.music_volume)
            pygame.mixer.music.play(loops=-1)
        except pygame.error:
            pass

    def play_sound(self, sound):
        if sound is None:
            return
        sound.set_volume(self.sfx_volume)
        sound.play()

    def play_jump_sound(self):
        self.play_sound(JUMP_SOUND)

    def play_wall_pass_sound(self):
        self.play_sound(WALL_PASS_SOUND)

    def play_crash_sound(self):
        self.play_sound(CRASH_SOUND)

    def play_gameover_sound(self):
        self.play_sound(GAMEOVER_SOUND)

    # ------------------------------------------------------------------
    # Collision
    # ------------------------------------------------------------------
    def circle_hits_wall(self, wall):
        wall_top = wall["y"]
        wall_bottom = wall["y"] + self.wall_thickness

        circle_bottom = self.player_y + self.player_radius
        circle_top = self.player_y - self.player_radius
        in_wall_height = circle_bottom > wall_top and circle_top < wall_bottom

        if not in_wall_height:
            return False

        gap_left = wall["gap_left"]
        gap_right = gap_left + self.wall_gap
        circle_left = self.player_x - self.player_radius
        circle_right = self.player_x + self.player_radius

        outside_gap = circle_left < gap_left or circle_right > gap_right
        return outside_gap

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self):
        self.draw_background()
        self.draw_walls()
        self.draw_particles()
        self.draw_jump_trails()
        self.draw_player()
        self.draw_score()
        self.draw_effects()
        self.draw_settings_icon()

        if not self.running:
            self.draw_menu()

        if self.settings_open:
            self.draw_settings_panel()

        pygame.display.flip()

    def get_layer_progress(self):
        """Find which two SKY_LAYERS stops the current score sits between.

        Returns (lo_name, hi_name, t, display_name) where t is 0..1 progress
        from the lo stop to the hi stop.
        """
        progress = self.points

        if progress <= SKY_LAYERS[0][0]:
            name = SKY_LAYERS[0][3]
            return name, name, 0.0, name

        if progress >= SKY_LAYERS[-1][0]:
            name = SKY_LAYERS[-1][3]
            return name, name, 0.0, name

        for (lo_points, _, _, lo_name, _), (hi_points, _, _, hi_name, _) in zip(
            SKY_LAYERS, SKY_LAYERS[1:]
        ):
            if lo_points <= progress <= hi_points:
                t = (progress - lo_points) / (hi_points - lo_points)
                display_name = lo_name if t < 0.5 else hi_name
                return lo_name, hi_name, t, display_name

        name = SKY_LAYERS[-1][3]
        return name, name, 0.0, name

    def get_current_layer_name(self):
        return self.get_layer_progress()[3]

    def get_background_surface(self):
        """Return a cross-faded surface between the two nearest sky layers.

        Cross-fades are cached by (lo_name, hi_name, rounded_t) since `points`
        only changes occasionally, so we don't redo the blend every frame.
        """
        lo_name, hi_name, t, _display_name = self.get_layer_progress()
        cache_key = (lo_name, hi_name, round(t, 2))

        cached = self._bg_surface_cache.get(cache_key)
        if cached is not None:
            return cached

        if lo_name == hi_name:
            blended = self.background_images[lo_name]
        else:
            base = self.background_images[lo_name].copy()
            top = self.background_images[hi_name].copy()
            top.set_alpha(int(t * 255))
            base.blit(top, (0, 0))
            blended = base

        self._bg_surface_cache[cache_key] = blended
        return blended

    def draw_background(self):
        self.current_bg_surface = self.get_background_surface()
        self.screen.blit(self.current_bg_surface, (0, 0))

    def draw_walls(self):
        for wall in self.walls:
            y = wall["y"] - self.camera_y
            gap_left = wall["gap_left"]
            gap_right = gap_left + self.wall_gap
            bottom = y + self.wall_thickness
            wall_color = hex_to_rgb("#39b98f" if wall["counted"] else "#d84a4a")
            wall_shadow = hex_to_rgb("#2b8e70" if wall["counted"] else "#9e2f35")

            if gap_left > 0:
                pygame.draw.rect(self.screen, wall_color, (0, y, gap_left, self.wall_thickness))
            if gap_right < WIDTH:
                pygame.draw.rect(self.screen, wall_color, (gap_right, y, WIDTH - gap_right, self.wall_thickness))

            shadow_top = bottom - 8
            if gap_left > 0:
                pygame.draw.rect(self.screen, wall_shadow, (0, shadow_top, gap_left, 8))
            if gap_right < WIDTH:
                pygame.draw.rect(self.screen, wall_shadow, (gap_right, shadow_top, WIDTH - gap_right, 8))

    def draw_particles(self):
        for particle in self.particles:
            screen_y = particle["y"] - self.camera_y
            pygame.draw.circle(
                self.screen,
                hex_to_rgb(particle["color"]),
                (int(particle["x"]), int(screen_y)),
                int(particle["size"]),
            )

    def draw_jump_trails(self):
        for trail in self.jump_trails:
            screen_y = trail["y"] - self.camera_y
            line_width = max(2, trail["life"] // 4)
            pygame.draw.line(
                self.screen,
                hex_to_rgb(trail["color"]),
                (trail["x"], screen_y),
                (trail["x"], screen_y + trail["length"]),
                line_width,
            )

    def draw_player(self):
        screen_y = self.player_y - self.camera_y
        pygame.draw.circle(
            self.screen, hex_to_rgb("#f7c948"),
            (int(self.player_x), int(screen_y)), self.player_radius,
        )
        pygame.draw.circle(
            self.screen, hex_to_rgb("#fff4bd"),
            (int(self.player_x), int(screen_y)), self.player_radius, 2,
        )

    def blit_text(self, font, text, color, pos, anchor="topleft"):
        surface = font.render(text, True, hex_to_rgb(color))
        rect = surface.get_rect(**{anchor: pos})
        self.screen.blit(surface, rect)

    def draw_score(self):
        self.blit_text(self.font_score, f"{self.points} pts", "#f6f1e8", (18, 24), anchor="midleft")
        self.blit_text(self.font_best, f"Best {self.best_score} pts", "#aebbd0", (18, 52), anchor="midleft")

    def draw_flame(self, x, y, flicker_seed):
        random.seed(flicker_seed)
        flicker = random.randint(-2, 2)
        random.seed()

        layers = [("#9e2f35", 12), ("#f08a4b", 9), ("#f7c948", 6), ("#fff4bd", 3)]
        for color, size in layers:
            rect = pygame.Rect(0, 0, size * 2, size * 2.3)
            rect.center = (x + flicker, y - size * 0.65)
            pygame.draw.ellipse(self.screen, hex_to_rgb(color), rect)

    def draw_effects(self):
        for effect in self.milestone_effects:
            age = effect["max_life"] - effect["life"]
            rise = age * 0.5
            self.draw_flame(96, 6 - rise, id(effect) + age // 3)
            self.blit_text(
                self.font_milestone, f"{effect['points']}!", "#fff4bd",
                (96, -14 - rise), anchor="midtop",
            )

        for effect in self.record_effects:
            age = effect["max_life"] - effect["life"]
            rise = age * 0.4
            self.draw_flame(150, 44 - rise, id(effect) + age // 3)
            self.blit_text(
                self.font_milestone, "New Record!", "#fff4bd",
                (150, 24 - rise), anchor="midtop",
            )

    def draw_settings_icon(self):
        x, y, r = self.gear_x, self.gear_y, self.gear_r
        pygame.draw.circle(self.screen, hex_to_rgb("#1d2b3a"), (x, y), r)
        pygame.draw.circle(self.screen, hex_to_rgb("#aebbd0"), (x, y), r, 2)
        self.blit_text(self.font_gear, "\u2699", "#f6f1e8", (x, y), anchor="center")

    def draw_settings_panel(self):
        p = self.panel
        panel_rect = pygame.Rect(p["x0"], p["y0"], p["x1"] - p["x0"], p["y1"] - p["y0"])
        pygame.draw.rect(self.screen, hex_to_rgb("#182333"), panel_rect)
        pygame.draw.rect(self.screen, hex_to_rgb("#aebbd0"), panel_rect, 2)

        self.blit_text(
            self.font_panel_title, "Settings", "#f6f1e8",
            ((p["x0"] + p["x1"]) / 2, p["y0"] + 24), anchor="midtop",
        )

        pygame.draw.circle(self.screen, hex_to_rgb("#d84a4a"), (self.close_x, self.close_y), 14)
        self.blit_text(self.font_close, "X", "#fff4bd", (self.close_x, self.close_y), anchor="center")

        self.draw_slider("Music", self.music_slider, self.music_volume)
        self.draw_slider("SFX", self.sfx_slider, self.sfx_volume)

    def draw_slider(self, label, track, value):
        self.blit_text(
            self.font_label, label, "#d4deea",
            (track["x0"] - 20, track["y"]), anchor="midright",
        )
        pygame.draw.line(
            self.screen, hex_to_rgb("#aebbd0"),
            (track["x0"], track["y"]), (track["x1"], track["y"]), 4,
        )
        handle_x = track["x0"] + value * (track["x1"] - track["x0"])
        pygame.draw.circle(self.screen, hex_to_rgb("#f7c948"), (int(handle_x), track["y"]), 9)
        pygame.draw.circle(self.screen, hex_to_rgb("#fff4bd"), (int(handle_x), track["y"]), 9, 2)

    def draw_menu(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((16, 23, 33, 160))
        self.screen.blit(overlay, (0, 0))

        if self.has_played:
            self.blit_text(
                self.font_menu_title, "Game Over!", "#f6f1e8",
                (WIDTH / 2, HEIGHT / 2 - 60), anchor="center",
            )
            self.blit_text(
                self.font_menu_score, f"Score: {self.points} pts", "#f7c948",
                (WIDTH / 2, HEIGHT / 2 - 12), anchor="center",
            )
            self.blit_text(
                self.font_menu_sub, "Tap to try again.", "#d4deea",
                (WIDTH / 2, HEIGHT / 2 + 28), anchor="center",
            )
        else:
            self.blit_text(
                self.font_menu_big_title, "Tap Tap Circle!!", "#f6f1e8",
                (WIDTH / 2, HEIGHT / 2 - 40), anchor="center",
            )
            self.blit_text(
                self.font_menu_sub, "Tap or press Space to jump", "#d4deea",
                (WIDTH / 2, HEIGHT / 2 + 8), anchor="center",
            )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def load_save_data(self):
        if not SAVE_FILE.exists():
            return {}
        try:
            with SAVE_FILE.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (json.JSONDecodeError, OSError):
            return {}

    def save_progress(self):
        data = {
            "best_score": self.best_score,
            "music_volume": self.music_volume,
            "sfx_volume": self.sfx_volume,
        }
        try:
            with SAVE_FILE.open("w", encoding="utf-8") as file:
                json.dump(data, file)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self):
        while self.app_running:
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(60)
        pygame.quit()


if __name__ == "__main__":
    game = TapCircleGame()
    game.run()