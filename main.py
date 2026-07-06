import json
import random
from pathlib import Path

from kivy.app import App
from kivy.uix.widget import Widget
from kivy.graphics import Line, Ellipse, Rectangle, Color
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.window import Window

# Set window size to match game dimensions
Window.size = (360, 640)

import os
os.environ['KIVY_AUDIO'] = 'ffpyplayer'


def get_asset_dir():
    """Return the folder to look for bundled assets in."""
    return Path(__file__).parent


ASSET_DIR = get_asset_dir()
if hasattr(App, 'user_data_dir'):
    SAVE_FILE = Path(App.get_running_app().user_data_dir) / "tap_circle_save.json"
else:
    SAVE_FILE = ASSET_DIR / "tap_circle_save.json"

WIDTH = 360
HEIGHT = 640

SKY_LAYERS = [
    (25, (135, 206, 250), (255, 241, 194), "Surface", "Surface.png"),
    (50, (100, 170, 235), (200, 224, 245), "Clouds", "Clouds.png"),
    (75, (58, 110, 190), (120, 150, 210), "Blue", "Blue.png"),
    (100, (25, 45, 90), (55, 65, 120), "Orbit", "Orbit.png"),
]


def load_sound(*filenames):
    """Try a few filename variants and return the first Sound that loads."""
    for name in filenames:
        path = ASSET_DIR / name
        if path.exists():
            try:
                return SoundLoader.load(str(path))
            except Exception:
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

print(f"[tap_circle] Assets in: {ASSET_DIR}")
print(f"[tap_circle] Sounds loaded: jump={JUMP_SOUND is not None}, wall_pass={WALL_PASS_SOUND is not None}, crash={CRASH_SOUND is not None}, gameover={GAMEOVER_SOUND is not None}, music={MUSIC_PATH is not None}")


class GameWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size = (WIDTH, HEIGHT)

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
        self.settings_open = False
        self.active_slider = None

        self.reset_game()
        Clock.schedule_interval(self.update, self.seconds_per_frame)

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
        self.milestone_effects = []

        for index in range(4):
            self.add_wall(-80 - index * self.wall_distance)

    def add_wall(self, y):
        padding = 46
        gap_left = random.randint(padding, WIDTH - self.wall_gap - padding)
        gap_direction = random.choice([-1, 1])
        self.walls.append({
            "y": y,
            "gap_left": gap_left,
            "gap_direction": gap_direction,
            "counted": False,
        })

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

    def on_touch_down(self, touch):
        if self.settings_open:
            self.handle_settings_touch(touch.pos[0], touch.pos[1])
            return True

        if not self.running:
            self.start_game()
            return True

        self.player_velocity_y = self.jump_power
        self.play_jump_sound()
        return True

    def handle_settings_touch(self, x, y):
        pass  # Simplified for now

    def update(self, dt):
        if not self.running or self.settings_open:
            self.canvas.clear()
            self.draw()
            return

        self.player_velocity_y += self.gravity
        self.player_y += self.player_velocity_y
        self.play_time += dt
        self.update_difficulty()
        self.update_camera()

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
                self.play_wall_pass_sound()

        self.update_particles()
        self.update_jump_trails()

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

        self.canvas.clear()
        self.draw()

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
        target_camera_y = self.player_y - self.camera_top_line
        if target_camera_y >= self.camera_y:
            return
        catch_up_rate = min(0.9, 0.05 * (self.wall_speed / self.start_wall_speed))
        self.camera_y += (target_camera_y - self.camera_y) * catch_up_rate

    def update_particles(self):
        for particle in self.particles:
            particle["x"] += particle["velocity_x"]
            particle["y"] += particle["velocity_y"]
            particle["velocity_y"] += 0.12
            particle["life"] -= 1
        self.particles = [p for p in self.particles if p["life"] > 0]

    def update_jump_trails(self):
        for trail in self.jump_trails:
            trail["y"] += 2.5
            trail["life"] -= 1
        self.jump_trails = [t for t in self.jump_trails if t["life"] > 0]

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

    def play_sound(self, sound):
        if sound:
            sound.volume = self.sfx_volume
            sound.play()

    def play_jump_sound(self):
        self.play_sound(JUMP_SOUND)

    def play_wall_pass_sound(self):
        self.play_sound(WALL_PASS_SOUND)

    def play_crash_sound(self):
        self.play_sound(CRASH_SOUND)

    def play_gameover_sound(self):
        self.play_sound(GAMEOVER_SOUND)

    def draw(self):
        with self.canvas:
            # Background
            Color(0.1, 0.15, 0.2)
            Rectangle(size=(WIDTH, HEIGHT))

            # Walls
            for wall in self.walls:
                y = wall["y"] - self.camera_y
                gap_left = wall["gap_left"]
                gap_right = gap_left + self.wall_gap

                wall_color = (0.22, 0.73, 0.56) if wall["counted"] else (0.85, 0.29, 0.29)
                Color(*wall_color)

                if gap_left > 0:
                    Rectangle(pos=(0, y), size=(gap_left, self.wall_thickness))
                if gap_right < WIDTH:
                    Rectangle(pos=(gap_right, y), size=(WIDTH - gap_right, self.wall_thickness))

            # Particles
            for particle in self.particles:
                screen_y = particle["y"] - self.camera_y
                Color(*particle["color"])
                Ellipse(pos=(particle["x"] - particle["size"], screen_y - particle["size"]),
                       size=(particle["size"] * 2, particle["size"] * 2))

            # Jump trails
            for trail in self.jump_trails:
                screen_y = trail["y"] - self.camera_y
                Color(*trail["color"])
                Line(points=[trail["x"], screen_y, trail["x"], screen_y + trail["length"]], width=2)

            # Player
            screen_y = self.player_y - self.camera_y
            Color(0.97, 0.79, 0.29)
            Ellipse(pos=(self.player_x - self.player_radius, screen_y - self.player_radius),
                   size=(self.player_radius * 2, self.player_radius * 2))
            Color(1, 0.96, 0.74)
            Line(circle=(self.player_x, screen_y, self.player_radius), width=2)

            # Score (simplified text rendering)
            Color(0.96, 0.94, 0.91)


class TapCircleApp(App):
    def build(self):
        self.title = "Tap Circle"
        game = GameWidget()
        return game


if __name__ == '__main__':
    TapCircleApp().run()
