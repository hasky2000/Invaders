"""800 x 600 のクラシックなインベーダーゲーム。pygame のみで動作する。"""

from __future__ import annotations

import math
import os
import random
import json
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

from pixel_font import PixelFont
from effects import Effects
from sound import SoundEffects
from controls import Gamepad, GamepadInput
from pixel_display import PixelDisplay
from settings import Settings, load_settings
from tutorial import (
    EXPLANATIONS, INSTRUCTIONS, MOVE_DISTANCE, PHASE_READ_TIME, STEP_TITLES,
    TutorialProgress, TutorialStep,
)
from extra_stage import (
    ExtraStage, EXTRA_REQUIRED_LIVES, EXTRA_ESCORT_COUNT, BEAM_CANNON_COLUMNS,
    BOSS_MAX_HP, BOSS_BULLET_SPEED, BOSS_BOMB_DAMAGE, BOSS_COLLISION_DAMAGE,
    EXTRA_BULLET_LIMIT,
)


WIDTH, HEIGHT = 800, 600
FPS = 60
WHITE = (225, 235, 240)
GREEN = (100, 240, 140)
CYAN = (100, 215, 245)
PINK = (245, 110, 150)
YELLOW = (250, 220, 120)
SPECIAL_COLOR = (255, 180, 65)
CURVED_BULLET_COLOR = (215, 155, 255)
ENEMY_BULLET_SPEED = 180
SPECIAL_BULLET_SPEED = 108
SPECIAL_BULLET_SWAY = 22
SPECIAL_BULLET_PERIOD = 2.4
PLAYER_SPEED = 260
EXTRA_PLAYER_SPEED = 180
EXTRA_PRECISE_SPEED = 90
EXTRA_PLAYER_TOP = 100
EXTRA_PLAYER_BOTTOM = 575
PLAYER_LIVES = 5
PLAYER_Y = 540
PLAYER_HITBOX_SIZE = 6
SHOT_COOLDOWN = 0.26
MAX_BULLETS_PER_BARREL = 2
BARREL_OFFSETS = (-9, 9)
# 通常プレイ、EXTRA、メニューの操作に割り当てたキーでは練習をスキップしない。
TUTORIAL_SKIP_EXCLUDED_KEYS = frozenset({
    pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN,
    pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d,
    pygame.K_SPACE, pygame.K_b, pygame.K_LSHIFT, pygame.K_RSHIFT,
    pygame.K_ESCAPE, pygame.K_F11,
    pygame.K_RETURN, pygame.K_F2, pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
})
TOTAL_PHASES = 3
ALIEN_ROWS = 6
ALIEN_COLUMNS = 10
ALIEN_COUNT = ALIEN_ROWS * ALIEN_COLUMNS
ALIEN_BASE_INTERVAL = 0.55
ALIEN_MAX_KILL_ACCELERATION = 0.128
ALIEN_WAVE_ACCELERATION = 0.015
ALIEN_MIN_INTERVAL = 0.22
BOMB_SPEED = 390
BOMB_MIN_SPEED = 90
BOMB_DECELERATION = 180
BOMB_RADIUS = 110
BLAST_DURATION = 0.45
WAVE_READY_TIME = 0.7
WAVE_CLEAR_TIME = 0.8
PATTERN_DURATION = 6.0
MOVEMENT_PATTERNS = ("SWAY", "RUSH", "WEAVE")
# 隊列の速度倍率と、行ごとの横揺れの速度倍率。
PHASE_THREE_MOTION = {"SWAY": (1.12, 1.35), "RUSH": (1.45, 1.8), "WEAVE": (1.22, 2.2)}
ROW_SWAY_STEP = 6
ROW_SWAY = ROW_SWAY_STEP * 2
ROW_SWAY_INTERVAL = 0.3
ROW_SWAY_PATTERN = (0, 1, 2, 1, 0, -1, -2, -1)
SQUAD_ROWS = 3
SQUAD_COLUMNS = 5
SQUAD_COUNT = 4
SQUAD_X_PATTERN = (0, 1, 2, 3, 2, 1, 0, -1, -2, -3, -2, -1)
SQUAD_Y_PATTERN = (0, 1, 2, 3, 4, 3, 2, 1, 0, -1, -2, -3, -4, -3, -2, -1)
SQUAD_MAX_X_OFFSET = 36
PHASE_THREE_START_Y = 88
PHASE_THREE_DESCENT = 12
FALL_DURATION = 0.6
FALL_INITIAL_SPEED = 40
FALL_GRAVITY = 180
EXPLOSION_DURATION = 0.45
SPECIAL_ATTACK_TURNS = 3
SPECIAL_REST_TURNS = 2
COMBO_DURATION = 2.0
BOMB_EXPLOSION_SCALE = 2.0

# 1 が描画するピクセル。各行の幅を揃えることで編集しやすくする。
ALIEN_PATTERNS = (
    (
        ("00011000", "00111100", "01111110", "11011011", "11111111", "00100100", "01011010", "10100101"),
        ("00011000", "00111100", "01111110", "11011011", "11111111", "01011010", "10000001", "01000010"),
    ),
    (
        ("00100100", "00011000", "00111100", "01111110", "11011011", "11111111", "10100101", "00100100"),
        ("00100100", "10011001", "10111101", "11111111", "11011011", "01111110", "00100100", "01000010"),
    ),
    (
        ("00111100", "11111111", "11111111", "11011011", "11111111", "00100100", "01011010", "10000001"),
        ("00111100", "11111111", "11111111", "11011011", "11111111", "01011010", "10000001", "01000010"),
    ),
)
PLAYER_PATTERN = (
    "00000100000",
    "00001110000",
    "00001110000",
    "01111111110",
    "11111111111",
    "11111111111",
    "11111111111",
)
HEART_PATTERN = (
    "0110110",
    "1111111",
    "1111111",
    "1111111",
    "0111110",
    "0011100",
    "0001000",
)
UFO_PATTERN = (
    "00001111110000",
    "00111111111100",
    "01111111111110",
    "11011011011011",
    "11111111111111",
    "00110011001100",
)


def pixel_sprite(pattern: tuple[str, ...], color: tuple[int, int, int], scale: int = 3) -> pygame.Surface:
    surface = pygame.Surface((len(pattern[0]) * scale, len(pattern) * scale), pygame.SRCALPHA)
    for y, row in enumerate(pattern):
        for x, pixel in enumerate(row):
            if pixel == "1":
                pygame.draw.rect(surface, color, (x * scale, y * scale, scale, scale))
    return surface


@dataclass
class Bullet:
    x: float
    y: float
    velocity: float
    friendly: bool
    horizontal_velocity: float = 0.0
    curve_amplitude: float = 0.0
    curve_phase: float = 0.0
    age: float = 0.0
    boss_bullet: bool = False

    @property
    def rect(self) -> pygame.Rect:
        if self.curve_amplitude or self.boss_bullet:
            return pygame.Rect(round(self.x) - 4, round(self.y) - 4, 8, 8)
        return pygame.Rect(round(self.x) - 2, round(self.y) - 6, 4, 12)

    def advance(self, dt: float) -> None:
        previous_age = self.age
        self.age += dt
        self.x += self.horizontal_velocity * dt
        if self.curve_amplitude:
            # 発射時に決まる波状の軌道。自機の位置は参照しない。
            frequency = math.tau / SPECIAL_BULLET_PERIOD
            self.x += self.curve_amplitude * (
                math.sin(frequency * self.age + self.curve_phase)
                - math.sin(frequency * previous_age + self.curve_phase)
            )
        self.y += self.velocity * dt


@dataclass
class Alien:
    rect: pygame.Rect
    row: int
    column: int
    special: bool = False
    squad: int = -1
    beam_cannon: bool = False

    @property
    def kind(self) -> int:
        return 0 if self.row == 0 else 1 if self.row < 3 else 2

    @property
    def points(self) -> int:
        return (30, 20, 10)[self.kind]


@dataclass
class Popup:
    position: tuple[int, int]
    text: str
    remaining: float = 0.65


@dataclass
class Bomb:
    x: float
    y: float
    speed: float = BOMB_SPEED

    def advance(self, dt: float) -> None:
        # 最低速度に達する前後を分けて積分し、フレームレートによる差を防ぐ。
        slowing_time = min(dt, max(0.0, self.speed - BOMB_MIN_SPEED) / BOMB_DECELERATION)
        distance = self.speed * slowing_time - BOMB_DECELERATION * slowing_time ** 2 / 2
        self.y -= distance + BOMB_MIN_SPEED * (dt - slowing_time)
        self.speed = max(BOMB_MIN_SPEED, self.speed - BOMB_DECELERATION * dt)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(round(self.x) - 5, round(self.y) - 7, 10, 14)


@dataclass
class Blast:
    center: tuple[int, int]
    remaining: float = BLAST_DURATION


@dataclass(frozen=True)
class EnemyFire:
    interval_min: float
    interval_max: float
    salvo: int
    speed: float
    limit: int


ENEMY_FIRE = (
    EnemyFire(0.80, 1.25, 1, ENEMY_BULLET_SPEED, 4),
    EnemyFire(0.52, 0.84, 2, ENEMY_BULLET_SPEED, 8),
    EnemyFire(0.30, 0.50, 3, ENEMY_BULLET_SPEED, 14),
)
FIRE_RELIEF_THRESHOLD = 8
FINAL_ENEMY_FIRE_INTERVAL = (1.8, 2.4)


def enemy_fire_intervals(phase: int, enemy_count: int) -> tuple[float, float]:
    """8機未満では、残り1機の発射レートまで敵数に比例して緩和する。"""
    fire = ENEMY_FIRE[phase - 1]
    progress = max(0.0, min(1.0, (FIRE_RELIEF_THRESHOLD - enemy_count) / (FIRE_RELIEF_THRESHOLD - 1)))
    # 間隔そのものではなく、その逆数（発射レート）を線形に変化させる。
    interval_min = 1 / ((1 - progress) / fire.interval_min + progress / FINAL_ENEMY_FIRE_INTERVAL[0])
    interval_max = 1 / ((1 - progress) / fire.interval_max + progress / FINAL_ENEMY_FIRE_INTERVAL[1])
    return interval_min, interval_max


@dataclass
class KillChain:
    kills: int = 0
    collision_kills: int = 0


@dataclass
class FallingAlien:
    sprite: pygame.Surface
    x: float
    y: float
    spin: float
    drift: float
    age: float = 0.0
    smoke_timer: float = 0.0
    chain: KillChain | None = None

    @property
    def image(self) -> pygame.Surface:
        return pygame.transform.rotate(self.sprite, self.spin * (self.age + 0.08))

    @property
    def center(self) -> tuple[int, int]:
        return (round(self.x), round(self.y))

    @property
    def rect(self) -> pygame.Rect:
        return self.image.get_rect(center=self.center)

    def advance(self, dt: float) -> None:
        self.x += self.drift * dt
        self.y += (FALL_INITIAL_SPEED + FALL_GRAVITY * self.age) * dt + FALL_GRAVITY * dt ** 2 / 2
        self.age += dt


@dataclass
class Explosion:
    """撃墜後の見た目だけの爆発。範囲攻撃の当たり判定は持たない。"""

    center: tuple[int, int]
    remaining: float = EXPLOSION_DURATION
    scale: float = 1.0


def circle_overlaps_rect(center: tuple[int, int], radius: int, rect: pygame.Rect) -> bool:
    """円に最も近い矩形上の点から、爆風が触れるかを判定する。"""
    closest_x = max(rect.left, min(center[0], rect.right))
    closest_y = max(rect.top, min(center[1], rect.bottom))
    return (center[0] - closest_x) ** 2 + (center[1] - closest_y) ** 2 <= radius ** 2


class Shield:
    """透明部分を含む防壁。弾が当たると、その周囲を円形に削る。"""

    def __init__(self, center_x: int) -> None:
        self.rect = pygame.Rect(center_x - 36, 452, 72, 48)
        self.image = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.polygon(self.image, GREEN, [(0, 16), (16, 0), (56, 0), (72, 16), (72, 48), (0, 48)])
        pygame.draw.rect(self.image, (0, 0, 0, 0), (24, 30, 24, 18))
        self.mask = pygame.mask.from_surface(self.image)

    def hit(self, bullet: Bullet) -> bool:
        if not self.rect.colliderect(bullet.rect):
            return False
        offset = (bullet.rect.x - self.rect.x, bullet.rect.y - self.rect.y)
        impact = self.mask.overlap(pygame.mask.Mask(bullet.rect.size, fill=True), offset)
        if impact is None:
            return False
        pygame.draw.circle(self.image, (0, 0, 0, 0), impact, 9)
        self.mask = pygame.mask.from_surface(self.image)
        return True

    def crush(self, alien_rect: pygame.Rect) -> None:
        if self.rect.colliderect(alien_rect):
            local_rect = alien_rect.move(-self.rect.x, -self.rect.y)
            pygame.draw.rect(self.image, (0, 0, 0, 0), local_rect)
            self.mask = pygame.mask.from_surface(self.image)


class Game:
    def __init__(
        self, screen: pygame.Surface, sounds: SoundEffects | None = None,
        *, settings: Settings | None = None,
    ) -> None:
        self.screen = screen
        self.settings = settings if settings is not None else load_settings()
        self.sounds = sounds if sounds is not None else SoundEffects(enabled=False)
        self.gamepad_name = ""
        self.gamepad_hint = ""
        # BMPなら拡張画像形式のないpygame環境でも読める。加工は起動時の一度だけ。
        background_path = Path(__file__).resolve().parent / "assets" / "milky-way.bmp"
        background = pygame.image.load(background_path).convert()
        background = pygame.transform.scale(background, (400, 300))
        self.background = pygame.transform.scale(background, (WIDTH, HEIGHT))
        self.background.fill((230, 230, 230), special_flags=pygame.BLEND_RGB_MULT)
        self.extra_background = self.background.copy()
        self.extra_background.fill((255, 64, 56), special_flags=pygame.BLEND_RGB_MULT)
        self.extra_background.fill((18, 0, 4), special_flags=pygame.BLEND_RGB_ADD)
        self.font = PixelFont(2)
        self.small_font = PixelFont(2)
        self.title_font = PixelFont(6)
        self.combo_font = PixelFont(3)
        pygame.font.init()
        japanese_font_path = Path(__file__).resolve().parent / "fonts" / "DotGothic16-Regular.ttf"
        if not japanese_font_path.is_file():
            raise RuntimeError(f"日本語フォントが見つかりません: {japanese_font_path}")
        self.japanese_font = pygame.font.Font(str(japanese_font_path), 24)
        self.japanese_text_cache: dict[tuple[str, tuple[int, int, int]], pygame.Surface] = {}
        self.held_keys: set[int] = set()
        self.player_image = pixel_sprite(PLAYER_PATTERN, GREEN)
        self.player_mask = pygame.mask.from_surface(self.player_image)
        self.heart_image = pixel_sprite(HEART_PATTERN, PINK, scale=2)
        self.alien_images = [
            [pixel_sprite(frame, (CYAN, GREEN, PINK)[kind]) for frame in frames]
            for kind, frames in enumerate(ALIEN_PATTERNS)
        ]
        self.special_alien_images = []
        for frames in ALIEN_PATTERNS:
            images = []
            for frame in frames:
                image = pixel_sprite(frame, SPECIAL_COLOR)
                # 色に加えて両端の白い角と紫のコアで見分けられるようにする。
                pygame.draw.polygon(image, WHITE, [(0, 0), (6, 6), (0, 6)])
                pygame.draw.polygon(image, WHITE, [(23, 0), (17, 6), (23, 6)])
                pygame.draw.rect(image, CURVED_BULLET_COLOR, (9, 12, 6, 6))
                images.append(image)
            self.special_alien_images.append(images)
        self.resting_alien_images = []
        for images in self.special_alien_images:
            resting = []
            for image in images:
                image = image.copy()
                image.fill((135, 145, 180), special_flags=pygame.BLEND_RGB_MULT)
                resting.append(image)
            self.resting_alien_images.append(resting)
        self.ufo_image = pixel_sprite(UFO_PATTERN, PINK)
        self.high_score = 0  # 今回の起動中のハイスコア。
        self.results_path = Path(__file__).resolve().parent / "results.json"
        self.results = self.load_results()
        self.run_elapsed = 0.0
        self.result_timer = 0.0
        self.current_result: dict | None = None
        self.reset()
        self.state = "title"

    @property
    def max_start_phase(self) -> int:
        return TOTAL_PHASES + int(self.settings.extra_enabled)

    def reset(self, start_phase: int = 1) -> None:
        start_phase = max(1, min(start_phase, self.max_start_phase))
        self.tutorial: TutorialProgress | None = None
        self.gamepad_bomb_armed = False
        self.sounds.pause(False)
        self.score = 0
        self.run_elapsed = 0.0
        self.current_result = None
        self.lives = PLAYER_LIVES
        self.start_phase = start_phase
        self.wave = min(start_phase, TOTAL_PHASES)
        self.player_x = WIDTH / 2
        self.player_y = float(PLAYER_Y)
        self.invincible = 0.0
        self.bullets: list[Bullet] = []
        self.popups: list[Popup] = []
        self.shields = [Shield(x) for x in (145, 315, 485, 655)]
        self.state = "playing"
        self.prepare_wave(extra=start_phase == 4)

    def load_results(self) -> list[dict]:
        try:
            data = json.loads(self.results_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def finish_run(self, outcome: str) -> None:
        if self.tutorial is not None:
            self.state = "game_over"
            return
        if self.state in ("results", "game_over", "victory"):
            return
        entry = {"score": self.score, "time": round(self.run_elapsed, 1), "outcome": outcome}
        self.results.append(entry)
        self.results.sort(key=lambda item: (-item["score"], item["time"]))
        self.result_rank = next(index for index, item in enumerate(self.results, 1) if item is entry)
        self.results = self.results[:100]
        try:
            self.results_path.write_text(json.dumps(self.results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
        self.current_result = entry
        self.result_timer = 12.0
        self.state = "results"

    def start_tutorial(self, gamepad: GamepadInput | None = None) -> None:
        self.reset()
        self.tutorial = TutorialProgress(blocked_keys=set(self.held_keys))
        if gamepad is not None:
            self.tutorial.block_pad_fire = gamepad.fire
            self.tutorial.block_pad_movement = any(gamepad.movement)
            self.tutorial.awaiting_pad_sample = False
        self.prepare_tutorial_step()

    def prepare_tutorial_step(self) -> None:
        """各課題を独立した練習にする。入力の長押し時間だけは課題間で維持する。"""
        tutorial = self.tutorial
        assert tutorial is not None
        self.state = "playing"
        tutorial.elapsed = 0.0
        tutorial.damage_shot_timer = 1.5
        tutorial.damage_taken = False
        tutorial.bomb_launched = False
        self.gamepad_bomb_armed = False
        self.lives = PLAYER_LIVES
        self.score = 0
        self.player_x = WIDTH / 2
        self.invincible = 0.0
        self.popups.clear()
        self.prepare_wave()
        self.shields.clear()
        self.bombs_left = 1 if tutorial.step == TutorialStep.BOMB else 0
        self.ready_timer = 0.0
        self.aliens = []
        if tutorial.enemy_count == 1:
            self.aliens = [Alien(pygame.Rect(388, 326, 24, 24), 0, 0)]
        elif tutorial.enemy_count == 4:
            self.aliens = [
                Alien(pygame.Rect(370 + column * 36, 326 + row * 32, 24, 24), row, column)
                for row in range(2) for column in range(2)
            ]
        if self.aliens:
            self.enemy_shot_timer = random.uniform(*enemy_fire_intervals(1, len(self.aliens)))

    def advance_tutorial(self) -> None:
        assert self.tutorial is not None
        if self.tutorial.step == TutorialStep.PHASES:
            self.tutorial.complete = True
            self.wave_timer = WAVE_CLEAR_TIME
            self.sounds.play("clear")
        else:
            self.tutorial.step = TutorialStep(self.tutorial.step + 1)
            self.prepare_tutorial_step()

    def confirm_tutorial(self) -> None:
        tutorial = self.tutorial
        if tutorial is not None and tutorial.step == TutorialStep.PHASES and not tutorial.complete:
            if tutorial.elapsed >= PHASE_READ_TIME:
                self.advance_tutorial()

    def update_tutorial_lesson(self, dt: float, distance: float) -> None:
        """敵のいない説明・被弾練習を進める。本編の被弾判定は共用する。"""
        tutorial = self.tutorial
        assert tutorial is not None
        if tutorial.step == TutorialStep.DAMAGE and not tutorial.damage_taken:
            tutorial.damage_shot_timer -= dt
            if tutorial.damage_shot_timer <= 0 and not self.bullets:
                self.bullets.append(Bullet(self.player_x, self.player_rect.top - 120, 100, False))
                tutorial.damage_shot_timer = 1.3
        self.update_bullets(dt)
        if tutorial.step == TutorialStep.MOVE:
            tutorial.record_movement(distance)
            if tutorial.movement_complete:
                self.advance_tutorial()
        elif tutorial.step == TutorialStep.FIRE and tutorial.shot_fired:
            self.advance_tutorial()
        elif tutorial.step == TutorialStep.DAMAGE and tutorial.damage_taken and self.invincible <= 0:
            self.advance_tutorial()

    def tutorial_input(
        self, dt: float, keys: pygame.key.ScancodeWrapper, gamepad: GamepadInput,
    ) -> tuple[set[int], GamepadInput]:
        """開始入力の持ち越しを除外し、キーごとの長押しを更新する。"""
        tutorial = self.tutorial
        assert tutorial is not None
        # KEYUPを取りこぼした場合も、現在のキーボード状態を正とする。
        self.held_keys = {key for key in self.held_keys if keys[key]}
        tutorial.blocked_keys.intersection_update(self.held_keys)
        # キーボードで開始した場合、同じフレームのパッド入力はここで初めて分かる。
        if tutorial.awaiting_pad_sample:
            tutorial.block_pad_fire = gamepad.fire
            tutorial.block_pad_movement = any(gamepad.movement)
            tutorial.awaiting_pad_sample = False
        if not gamepad.fire:
            tutorial.block_pad_fire = False
        if not any(gamepad.movement):
            tutorial.block_pad_movement = False
        allowed = self.held_keys - tutorial.blocked_keys
        pad = GamepadInput(
            movement=(0.0, 0.0) if tutorial.block_pad_movement else gamepad.movement,
            fire=gamepad.fire and not tutorial.block_pad_fire,
        )
        if tutorial.update_holds(dt, allowed - TUTORIAL_SKIP_EXCLUDED_KEYS):
            self.reset()
        return tutorial.blocked_keys, pad

    @property
    def player_rect(self) -> pygame.Rect:
        rect = self.player_image.get_rect()
        rect.midbottom = (round(self.player_x), round(self.player_y) + self.player_image.get_height())
        return rect

    @property
    def player_hitbox(self) -> pygame.Rect:
        """EXTRAは中央の小判定、それ以外は画像に沿う判定の外接矩形。"""
        if self.extra_stage is None:
            return self.player_rect
        hitbox = pygame.Rect(0, 0, PLAYER_HITBOX_SIZE, PLAYER_HITBOX_SIZE)
        hitbox.center = self.player_rect.center
        return hitbox

    def player_is_hit(self, bullet_rect: pygame.Rect) -> bool:
        """通常・練習では画像の透明部分を除き、EXTRAでは小判定を使う。"""
        if self.extra_stage is not None:
            return bullet_rect.colliderect(self.player_hitbox)
        player_rect = self.player_rect
        if not bullet_rect.colliderect(player_rect):
            return False
        bullet_mask = pygame.mask.Mask(bullet_rect.size, fill=True)
        offset = (bullet_rect.left - player_rect.left, bullet_rect.top - player_rect.top)
        return self.player_mask.overlap(bullet_mask, offset) is not None

    def create_formation(self) -> list[Alien]:
        start_y = 112 + min(self.wave - 1, 5) * 12
        start_x = (WIDTH - ((ALIEN_COLUMNS - 1) * 52 + 24)) // 2
        aliens = []
        for row in range(ALIEN_ROWS):
            for column in range(ALIEN_COLUMNS):
                squad = -1
                if self.wave == 1:
                    # 千鳥配置にして、落下機が次の行の複数機に触れやすくする。
                    x = 217 + column * 36 + (row % 2) * 18
                    y = 112 + row * 32
                elif self.wave == 3:
                    squad = (row // SQUAD_ROWS) * 2 + column // SQUAD_COLUMNS
                    x = 176 + (squad % 2) * 280 + (column % SQUAD_COLUMNS) * 36
                    y = PHASE_THREE_START_Y + (squad // 2) * 176 + (row % SQUAD_ROWS) * 30
                else:
                    x = start_x + column * 52
                    y = start_y + row * 40
                aliens.append(Alien(
                    pygame.Rect(x, y, 24, 24), row, column,
                    special=self.wave == 3 and (column - row) % 5 == 2, squad=squad,
                ))
        return aliens

    def prepare_wave(self, *, extra: bool = False) -> None:
        extra = extra and self.settings.extra_enabled
        self.extra_stage = ExtraStage() if extra else None
        self.player_y = float(PLAYER_Y)
        if self.extra_stage is None:
            self.aliens = self.create_formation()
        else:
            self.lives = PLAYER_LIVES
            self.shields.clear()
            self.player_x = WIDTH / 2
            self.invincible = 0.0
            self.aliens = []
            for column in range(EXTRA_ESCORT_COUNT):
                cannon = column in BEAM_CANNON_COLUMNS
                size = (30, 36) if cannon else (24, 24)
                rect = pygame.Rect((0, 0), size)
                rect.center = self.extra_stage.escort_center(column)
                self.aliens.append(Alien(rect, 2, column, beam_cannon=cannon))
        self.direction = 1
        self.alien_timer = 0.0
        self.alien_frame = 0
        self.phase_elapsed = 0.0
        self.row_offsets = [0] * ALIEN_ROWS
        self.row_sway_elapsed = 0.0
        self.squad_elapsed = 0.0
        self.squad_offsets = [(0, 0)] * SQUAD_COUNT
        fire = ENEMY_FIRE[self.wave - 1]
        self.enemy_shot_timer = random.uniform(fire.interval_min, fire.interval_max)
        self.special_fire_turn = 0
        self.special_resting = False
        self.combo_count = 0
        self.combo_timer = 0.0
        self.combo_chain: KillChain | None = None
        self.ufo_x: float | None = None
        self.ufo_timer = random.uniform(15, 23)
        self.bullets.clear()
        self.shot_timer = 0.0
        self.next_barrel = 0
        self.bombs_left = self.wave
        self.bomb: Bomb | None = None
        self.blasts: list[Blast] = []
        self.falling_aliens: list[FallingAlien] = []
        self.explosions: list[Explosion] = []
        self.effects = Effects()
        self.wave_timer = 0.0
        self.ready_timer = 1.4 if extra else WAVE_READY_TIME

    def add_score(self, points: int) -> None:
        if self.tutorial is not None:
            return
        self.score += points
        self.high_score = max(self.high_score, self.score)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """False を返した場合は、メインループを終了する。"""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.WINDOWFOCUSLOST and self.state == "playing":
            self.held_keys.clear()
        if event.type == pygame.KEYUP:
            self.held_keys.discard(event.key)
            if self.tutorial is not None:
                self.tutorial.blocked_keys.discard(event.key)
                self.tutorial.hold_times.pop(event.key, None)
        if event.type != pygame.KEYDOWN:
            return True
        self.held_keys.add(event.key)
        if getattr(event, "repeat", False):
            return True
        if event.key == pygame.K_ESCAPE:
            return False
        if event.key == pygame.K_F2 and self.state in ("title", "debug", "game_over", "victory"):
            self.state = "title" if self.state == "debug" else "debug"
        elif self.state == "title" and event.key != pygame.K_F11:
            self.start_tutorial()
        elif self.state == "debug" and event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
            phase = event.key - pygame.K_0
            if phase <= self.max_start_phase:
                self.start_phase = phase
        elif self.state in ("debug", "game_over", "victory") and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.reset(start_phase=self.start_phase if self.state == "debug" else 1)
        elif self.tutorial is not None and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.confirm_tutorial()
        elif event.key == pygame.K_b and not getattr(event, "repeat", False):
            self.launch_bomb()
        return True

    def handle_gamepad(self, gamepad: GamepadInput) -> None:
        # 非プレイ中から持ち越したボムは、一度離してから再び押すまで無効。
        if not gamepad.bomb_held:
            self.gamepad_bomb_armed = True
        elif self.state != "playing" or (
            self.tutorial is not None and self.tutorial.step != TutorialStep.BOMB
        ) or self.ready_timer > 0 or self.wave_timer > 0:
            self.gamepad_bomb_armed = False

        # 状態遷移を先に処理し、同じフレームのボムを遷移先へ持ち込まない。
        is_menu = self.state in ("title", "debug", "game_over", "victory")
        if "disconnected" in gamepad.actions:
            self.gamepad_bomb_armed = False
            return
        if self.tutorial is not None and self.tutorial.step == TutorialStep.PHASES:
            if "confirm" in gamepad.actions or "start" in gamepad.actions:
                self.confirm_tutorial()
            return
        if "start" in gamepad.actions or ("confirm" in gamepad.actions and is_menu):
            if is_menu:
                self.start_menu_game(gamepad)
            self.gamepad_bomb_armed = not gamepad.bomb_held
            return

        for action in gamepad.actions:
            if action in ("previous_phase", "next_phase") and self.state == "debug":
                direction = 1 if action == "next_phase" else -1
                self.start_phase = (self.start_phase - 1 + direction) % self.max_start_phase + 1
            elif action == "bomb" and self.gamepad_bomb_armed:
                self.gamepad_bomb_armed = False
                self.launch_bomb()

    def start_menu_game(self, gamepad: GamepadInput) -> None:
        if self.state == "title":
            self.start_tutorial(gamepad)
        else:
            self.reset(start_phase=self.start_phase if self.state == "debug" else 1)

    def update(self, dt: float, keys: pygame.key.ScancodeWrapper, gamepad: GamepadInput | None = None) -> None:
        if self.state == "results":
            self.result_timer -= dt
            if self.result_timer <= 0:
                self.start_tutorial()
            return
        if self.state != "playing":
            return
        if self.tutorial is None:
            self.run_elapsed += dt
        gamepad = gamepad if gamepad is not None else GamepadInput()
        blocked_keys: set[int] = set()
        if self.tutorial is not None:
            blocked_keys, gamepad = self.tutorial_input(dt, keys, gamepad)
            if self.tutorial is None:  # スキップ後の本編を同じ入力で動かさない。
                return
            self.tutorial.elapsed += dt
        self.combo_timer = max(0.0, self.combo_timer - dt)
        self.effects.update(dt)
        for explosion in self.explosions[:]:
            explosion.remaining -= dt
            if explosion.remaining <= 0:
                self.explosions.remove(explosion)
        for blast in self.blasts[:]:
            blast.remaining -= dt
            if blast.remaining <= 0:
                self.blasts.remove(blast)
        for popup in self.popups[:]:
            popup.remaining -= dt
            if popup.remaining <= 0:
                self.popups.remove(popup)
        if self.wave_timer > 0:
            self.wave_timer -= dt
            if self.wave_timer <= 0:
                if self.tutorial is not None:
                    self.reset()
                elif self.wave == TOTAL_PHASES:
                    if self.settings.extra_enabled and self.extra_stage is None and self.lives >= EXTRA_REQUIRED_LIVES:
                        self.prepare_wave(extra=True)
                    else:
                        self.finish_run("clear")
                        self.sounds.play("victory")
                else:
                    self.wave += 1
                    self.prepare_wave()
            return
        if self.ready_timer > 0:
            self.ready_timer -= dt
            return

        self.invincible = max(0.0, self.invincible - dt)
        self.shot_timer = max(0.0, self.shot_timer - dt)
        def pressed(key: int) -> bool:
            return key not in blocked_keys and keys[key]

        horizontal = int(pressed(pygame.K_RIGHT) or pressed(pygame.K_d)) - int(pressed(pygame.K_LEFT) or pressed(pygame.K_a)) + gamepad.movement[0]
        vertical = 0
        speed = PLAYER_SPEED
        if self.extra_stage is not None:
            vertical = int(keys[pygame.K_DOWN] or keys[pygame.K_s]) - int(keys[pygame.K_UP] or keys[pygame.K_w]) + gamepad.movement[1]
            precise = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] or gamepad.precise
            speed = EXTRA_PRECISE_SPEED if precise else EXTRA_PLAYER_SPEED
        movement = pygame.Vector2(horizontal, vertical)
        if movement.length_squared() > 1:
            movement.normalize_ip()
        half_width = self.player_image.get_width() / 2
        previous_x = self.player_x
        self.player_x = max(28 + half_width, min(WIDTH - 28 - half_width, self.player_x + movement.x * speed * dt))
        if self.extra_stage is not None:
            max_y = EXTRA_PLAYER_BOTTOM - self.player_image.get_height()
            self.player_y = max(EXTRA_PLAYER_TOP, min(max_y, self.player_y + movement.y * speed * dt))
        auto_fire = self.extra_stage is not None and self.extra_stage.boss.alive
        if (pressed(pygame.K_SPACE) or gamepad.fire or auto_fire) and (
            self.tutorial is None or self.tutorial.allows_fire
        ):
            self.fire()

        if self.tutorial is not None and self.tutorial.enemy_count == 0:
            self.update_tutorial_lesson(dt, self.player_x - previous_x)
            return

        if self.extra_stage is not None:
            self.update_extra_stage(dt)
        else:
            self.move_aliens(dt)
        if self.state != "playing":
            if self.tutorial is not None:
                self.prepare_tutorial_step()
            return
        self.update_enemy_fire(dt)
        if self.extra_stage is None and self.tutorial is None:
            self.update_ufo(dt)
        self.update_bomb(dt)
        self.update_bullets(dt)
        self.update_falling_aliens(dt)
        if self.tutorial is not None:
            if self.state == "game_over":
                self.prepare_tutorial_step()
            elif self.tutorial.step == TutorialStep.BOMB and not self.aliens and not self.tutorial.bomb_launched:
                self.prepare_tutorial_step()
            elif not self.aliens:
                self.bullets.clear()
                if not self.falling_aliens and not self.explosions and not self.blasts:
                    self.advance_tutorial()
            elif self.tutorial.step == TutorialStep.BOMB and self.bomb is None and not self.blasts:
                self.bombs_left = 1  # 外しても練習を続けられるよう補充する。
            return
        boss_defeated = self.extra_stage is None or not self.extra_stage.boss.alive
        if self.state == "playing" and not self.aliens and boss_defeated:
            self.bullets.clear()
            self.bomb = None
            if not self.falling_aliens and not self.explosions:
                self.wave_timer = WAVE_CLEAR_TIME
                self.sounds.play("clear")

    def fire(self) -> None:
        barrel_count = 2 if self.wave == 3 or self.extra_stage is not None else 1
        max_bullets = MAX_BULLETS_PER_BARREL * barrel_count
        if self.shot_timer > 0 or sum(bullet.friendly for bullet in self.bullets) >= max_bullets:
            return
        offset = BARREL_OFFSETS[self.next_barrel] if barrel_count == 2 else 0
        self.bullets.append(Bullet(self.player_x + offset, self.player_rect.top - 8, -510, True))
        if self.tutorial is not None and self.tutorial.step == TutorialStep.FIRE:
            self.tutorial.shot_fired = True
        # 2門を半周期ずらして交互に撃つ。各砲の発射間隔は単装時と同じ。
        self.next_barrel = (self.next_barrel + 1) % barrel_count
        self.shot_timer = SHOT_COOLDOWN / barrel_count
        self.sounds.play("shoot")

    @property
    def movement_pattern(self) -> str:
        if self.extra_stage is not None:
            return "BOSS"
        if self.wave == 1:
            return "CLASSIC"
        if self.wave == 2:
            return "ROWS"
        return MOVEMENT_PATTERNS[int(self.phase_elapsed / PATTERN_DURATION) % len(MOVEMENT_PATTERNS)]

    def update_extra_stage(self, dt: float) -> None:
        stage = self.extra_stage
        for sound in stage.advance(dt, self.aliens, self.player_hitbox.center):
            self.sounds.play(sound)
        if stage.hits_player(self.player_hitbox):
            # 即死ビームは通常被弾後の無敵時間でも防げない。
            self.lives = 0
            self.finish_run("game_over")
            self.effects.explode(self.player_hitbox.center)
            self.sounds.play("player_hit")
            self.sounds.play("game_over")
            return
        boss = stage.boss
        if not boss.alive:
            return
        boss.shot_timer -= dt
        if boss.shot_timer <= 1e-9:
            shots = boss.barrage_shots(BOSS_BULLET_SPEED)
            available = EXTRA_BULLET_LIMIT - sum(not bullet.friendly for bullet in self.bullets)
            if available >= len(shots):
                boss.shot_timer = boss.barrage_interval
                boss.last_barrage_pattern = boss.barrage_pattern
                boss.volley_index += 1
                for shot in shots:
                    vx, vy = shot.velocity
                    self.bullets.append(Bullet(
                        boss.rect.centerx + shot.offset[0], boss.rect.centery + shot.offset[1], vy, False,
                        horizontal_velocity=vx, boss_bullet=True,
                    ))
                self.sounds.play("enemy_shot")
            else:
                # 弾数上限で模様が欠けないよう、一斉射撃できる空きを待つ。
                boss.shot_timer = 0.1

    def damage_boss(self, damage: int) -> None:
        if self.extra_stage is None or not self.extra_stage.boss.alive:
            return
        boss = self.extra_stage.boss
        boss.hp = max(0, boss.hp - damage)
        boss.hit_flash = 0.1
        self.sounds.play("hit")
        if boss.alive:
            return
        self.add_score(2000)
        for dx, dy in ((0, 0), (-50, -20), (50, -20), (-35, 25), (35, 25)):
            center = (boss.rect.centerx + dx, boss.rect.centery + dy)
            self.explosions.append(Explosion(center, scale=1.8))
            self.effects.explode(center, scale=1.5)
        # ボス撃破で取り巻きも崩壊し、残った攻撃を止める。
        for alien in self.aliens[:]:
            self.down_alien(alien)
        self.extra_stage.cannons.clear()
        self.bullets = [bullet for bullet in self.bullets if bullet.friendly]
        self.sounds.play("bomb_explosion")

    def move_aliens(self, dt: float) -> None:
        if not self.aliens:
            return
        self.phase_elapsed += dt
        # 撃破時・ウェーブ進行時の加速を抑え、終盤も狙って撃てる速さにする。
        interval = max(
            ALIEN_MIN_INTERVAL,
            ALIEN_BASE_INTERVAL
            - (1 - len(self.aliens) / ALIEN_COUNT) * ALIEN_MAX_KILL_ACCELERATION
            - (self.wave - 1) * ALIEN_WAVE_ACCELERATION,
        )
        if self.wave == 1:
            self.move_formation(dt, interval)
        else:
            self.move_rows(dt, interval)
        for alien in self.aliens:
            for shield in self.shields:
                shield.crush(alien.rect)
        if any(alien.rect.bottom >= self.player_rect.top for alien in self.aliens):
            self.finish_run("game_over")
            self.sounds.play("game_over")

    def move_formation(
        self, dt: float, interval: float, *, horizontal_margin: int = 28, descent_step: int = 22,
    ) -> None:
        """フェーズ1は従来どおり、隊列全体が同時に移動・折り返しする。"""
        self.alien_timer += dt
        if self.alien_timer < interval:
            return
        self.alien_timer -= interval
        self.alien_frame = 1 - self.alien_frame
        step = 12 * self.direction
        at_edge = any(
            alien.rect.left + step < horizontal_margin
            or alien.rect.right + step > WIDTH - horizontal_margin
            for alien in self.aliens
        )
        if at_edge:
            self.direction *= -1
        for alien in self.aliens:
            alien.rect.move_ip(0 if at_edge else step, descent_step if at_edge else 0)

    def move_rows(self, dt: float, interval: float) -> None:
        """共通の隊列移動に、行ごとに周期の異なる段階的な横揺れを重ねる。"""
        formation_speed, sway_speed = (1.0, 1.0)
        sway_pattern = ROW_SWAY_PATTERN
        sway_limit = ROW_SWAY
        if self.wave == 3:
            formation_speed, sway_speed = PHASE_THREE_MOTION[self.movement_pattern]
            sway_pattern = (0, 1, 2, 3, 2, 1, 0, -1, -2, -3, -2, -1)
            sway_limit = ROW_SWAY_STEP * 3
            self.squad_elapsed += dt
        self.row_sway_elapsed += dt * sway_speed
        sway_time = self.row_sway_elapsed if self.wave == 3 else self.phase_elapsed
        # 前フレームの揺れを取り除いてから隊列を動かし、ずれの累積を防ぐ。
        for alien in self.aliens:
            alien.rect.x -= self.row_offsets[alien.row]
            if alien.squad >= 0:
                dx, dy = self.squad_offsets[alien.squad]
                alien.rect.move_ip(-dx, -dy)
        # 画面端に揺れ幅を確保し、折り返しと下降は隊列全体で行う。
        squad_margin = SQUAD_MAX_X_OFFSET if self.wave == 3 else 0
        self.move_formation(
            dt * formation_speed, interval, horizontal_margin=28 + sway_limit + squad_margin,
            descent_step=PHASE_THREE_DESCENT if self.wave == 3 else 22,
        )
        for row in range(ALIEN_ROWS):
            # 各段階の位置を保ち、一定間隔で6pxずつ動かす。
            step = int((sway_time + 1e-9) * (1 + row * 0.1) / ROW_SWAY_INTERVAL)
            direction = 1 if row % 2 == 0 else -1
            self.row_offsets[row] = ROW_SWAY_STEP * sway_pattern[step % len(sway_pattern)] * direction
        if self.wave == 3:
            for squad in range(SQUAD_COUNT):
                # 小隊ごとに周期をずらし、上下の小隊が接近する時間を限定する。
                x_step = int((self.squad_elapsed + 1e-9) * (1 + squad * 0.13) / 0.3)
                y_step = int((self.squad_elapsed + 1e-9) * (1 + squad * 0.11) / 0.4)
                x_direction = 1 if squad % 2 == 0 else -1
                y_direction = 1 if squad < 2 else -1
                dy = 6 * SQUAD_Y_PATTERN[y_step % len(SQUAD_Y_PATTERN)] * y_direction
                # 上下の小隊は互いに近づいてから戻る。下側を自機へ押し出さない。
                dy = max(0, dy) if squad < 2 else min(0, dy)
                self.squad_offsets[squad] = (
                    12 * SQUAD_X_PATTERN[x_step % len(SQUAD_X_PATTERN)] * x_direction,
                    dy,
                )
        for alien in self.aliens:
            alien.rect.x += self.row_offsets[alien.row]
            if alien.squad >= 0:
                alien.rect.move_ip(self.squad_offsets[alien.squad])

    def launch_bomb(self) -> None:
        if (
            self.state != "playing"
            or (self.tutorial is not None and self.tutorial.step != TutorialStep.BOMB)
            or self.ready_timer > 0
            or self.wave_timer > 0
            or (not self.aliens and (self.extra_stage is None or not self.extra_stage.boss.alive))
            or self.bombs_left <= 0
            or self.bomb is not None
        ):
            return
        self.bomb = Bomb(self.player_x, self.player_rect.top - 10)
        self.bombs_left -= 1
        if self.tutorial is not None:
            self.tutorial.bomb_launched = True
        self.sounds.play("bomb_launch")

    def update_bomb(self, dt: float) -> None:
        if self.bomb is None:
            return
        self.bomb.advance(dt)
        hit_enemy = any(self.bomb.rect.colliderect(alien.rect) for alien in self.aliens)
        if self.extra_stage is not None and self.extra_stage.boss.alive:
            hit_enemy = hit_enemy or self.bomb.rect.colliderect(self.extra_stage.boss.rect)
        if self.ufo_x is not None:
            ufo_rect = self.ufo_image.get_rect(topleft=(round(self.ufo_x), 68))
            hit_enemy = hit_enemy or self.bomb.rect.colliderect(ufo_rect)
        # 防壁は通過する。敵を外しても画面上部で爆発し、上端へ出ていかない。
        if hit_enemy or self.bomb.y <= 90:
            center = (round(self.bomb.x), round(max(90, self.bomb.y)))
            self.bomb = None
            self.explode_bomb(center)

    def explode_bomb(self, center: tuple[int, int]) -> None:
        self.blasts.append(Blast(center))
        self.effects.explode(center, scale=BOMB_EXPLOSION_SCALE)
        self.sounds.play("bomb_explosion")
        previous_score = self.score
        chain = KillChain()
        for alien in self.aliens[:]:
            if circle_overlaps_rect(center, BOMB_RADIUS, alien.rect):
                self.down_alien(alien, chain=chain)
        if self.extra_stage is not None and self.extra_stage.boss.alive:
            if circle_overlaps_rect(center, BOMB_RADIUS, self.extra_stage.boss.rect):
                self.damage_boss(BOSS_BOMB_DAMAGE)
        if self.ufo_x is not None:
            ufo_rect = self.ufo_image.get_rect(topleft=(round(self.ufo_x), 68))
            if circle_overlaps_rect(center, BOMB_RADIUS, ufo_rect):
                self.down_ufo(chain=chain)
        points = self.score - previous_score
        if points:
            self.popups.append(Popup(center, str(points)))
        self.bullets = [
            bullet for bullet in self.bullets
            if bullet.friendly or not circle_overlaps_rect(center, BOMB_RADIUS, bullet.rect)
        ]

    def update_enemy_fire(self, dt: float) -> None:
        self.enemy_shot_timer -= dt
        if self.enemy_shot_timer > 0 or not self.aliens:
            return
        if self.wave == 3:
            self.special_resting = self.special_fire_turn >= SPECIAL_ATTACK_TURNS
            self.special_fire_turn = (self.special_fire_turn + 1) % (SPECIAL_ATTACK_TURNS + SPECIAL_REST_TURNS)
        fire = ENEMY_FIRE[self.wave - 1]
        self.enemy_shot_timer = random.uniform(*enemy_fire_intervals(self.wave, len(self.aliens)))
        available = fire.limit - sum(not bullet.friendly and not bullet.boss_bullet for bullet in self.bullets)
        if self.extra_stage is not None:
            available = min(available, EXTRA_BULLET_LIMIT - sum(not bullet.friendly for bullet in self.bullets))
        if available <= 0:
            return
        # 各列の最下段からのみ発射し、味方の敵を弾が貫通する見た目を防ぐ。
        front_line: dict[int, Alien] = {}
        for alien in self.aliens:
            if alien.column not in front_line or alien.rect.bottom > front_line[alien.column].rect.bottom:
                front_line[alien.column] = alien
        candidates = [
            alien for alien in front_line.values()
            if not alien.beam_cannon and not (alien.special and self.special_resting)
        ]
        if not candidates:
            return
        special_candidates = [alien for alien in candidates if alien.special]
        shooter_count = min(fire.salvo, available, len(candidates))
        if self.wave == 3 and special_candidates:
            # 最前列に特殊敵がいれば、1機は曲線弾を撃つようにする。
            special = random.choice(special_candidates)
            others = [alien for alien in candidates if alien is not special]
            shooters = [special] + random.sample(others, shooter_count - 1)
        else:
            shooters = random.sample(candidates, shooter_count)
        bullets_before = len(self.bullets)
        for shooter in shooters:
            if available <= 0:
                break
            if self.wave == 3 and shooter.special:
                for lane in (0, -1, 1):
                    if available <= 0:
                        break
                    self.bullets.append(Bullet(
                        shooter.rect.centerx, shooter.rect.bottom + 8, SPECIAL_BULLET_SPEED, False,
                        horizontal_velocity=lane * 28, curve_amplitude=SPECIAL_BULLET_SWAY,
                        curve_phase=(shooter.column % 2) * math.pi,
                    ))
                    available -= 1
            else:
                self.bullets.append(Bullet(shooter.rect.centerx, shooter.rect.bottom + 8, fire.speed, False))
                available -= 1
        if len(self.bullets) > bullets_before:
            self.sounds.play("enemy_shot")

    def update_ufo(self, dt: float) -> None:
        if self.ufo_x is None:
            self.ufo_timer -= dt
            if self.ufo_timer <= 0:
                self.ufo_x = -self.ufo_image.get_width()
        else:
            self.ufo_x += 110 * dt
            if self.ufo_x > WIDTH:
                self.ufo_x = None
                self.ufo_timer = random.uniform(15, 23)

    def update_bullets(self, dt: float) -> None:
        for bullet in self.bullets:
            bullet.advance(dt)

        for bullet in self.bullets[:]:
            if bullet not in self.bullets:
                continue
            if bullet.rect.bottom < 55 or bullet.rect.top > 576 or bullet.rect.right < 0 or bullet.rect.left > WIDTH:
                self.bullets.remove(bullet)
                continue
            if any(shield.hit(bullet) for shield in self.shields):
                self.bullets.remove(bullet)
                continue
            if bullet.friendly:
                self.resolve_player_bullet(bullet)
            elif self.player_is_hit(bullet.rect):
                self.bullets.remove(bullet)
                if self.invincible <= 0:
                    self.lives -= 1
                    self.sounds.play("player_hit")
                    self.invincible = 1.8
                    if self.tutorial is not None and self.tutorial.step == TutorialStep.DAMAGE:
                        self.tutorial.damage_taken = True
                    self.popups.append(Popup(self.player_rect.center, "*"))
                    if self.lives <= 0:
                        self.finish_run("game_over")
                        self.sounds.play("game_over")
                        break

    def resolve_player_bullet(self, bullet: Bullet) -> None:
        for alien in self.aliens:
            if bullet.rect.colliderect(alien.rect):
                self.down_alien(alien)
                self.bullets.remove(bullet)
                return
        if self.extra_stage is not None and self.extra_stage.boss.alive:
            if bullet.rect.colliderect(self.extra_stage.boss.rect):
                self.damage_boss(1)
                self.bullets.remove(bullet)
                return
        if self.ufo_x is not None:
            ufo_rect = self.ufo_image.get_rect(topleft=(round(self.ufo_x), 68))
            if bullet.rect.colliderect(ufo_rect):
                points = self.down_ufo()
                self.popups.append(Popup(ufo_rect.center, str(points)))
                self.bullets.remove(bullet)

    def start_falling(self, sprite: pygame.Surface, center: tuple[int, int], chain: KillChain | None = None) -> None:
        self.falling_aliens.append(FallingAlien(
            sprite, center[0], center[1],
            spin=random.choice((-180, 180)), drift=random.uniform(-12, 12),
            chain=chain if chain is not None else KillChain(),
        ))
        self.effects.trail(center)

    def down_alien(self, alien: Alien, chain: KillChain | None = None, *, collision: bool = False) -> None:
        """敵を隊列から外し、得点と落下演出を一度だけ発生させる。"""
        if alien not in self.aliens:
            return
        previous_interval_min, _ = enemy_fire_intervals(self.wave, len(self.aliens))
        self.aliens.remove(alien)
        if self.aliens and self.enemy_shot_timer > 0:
            interval_min, _ = enemy_fire_intervals(self.wave, len(self.aliens))
            # 次の発射までの残り時間にも緩和を反映し、待ち時間の進み具合を保つ。
            self.enemy_shot_timer *= interval_min / previous_interval_min
        self.add_score(alien.points)
        chain = chain if chain is not None else KillChain()
        self.count_chain_kill(chain, collision=collision)
        self.start_falling(self.alien_image(alien), alien.rect.center, chain=chain)
        if self.extra_stage is not None:
            self.extra_stage.remove_escort(alien.column)
        self.sounds.play("hit")

    def count_chain_kill(self, chain: KillChain, *, collision: bool) -> None:
        chain.kills += 1
        chain.collision_kills += int(collision)
        if chain.collision_kills and (
            self.combo_chain is chain or self.combo_timer <= 0 or chain.kills >= self.combo_count
        ):
            self.combo_chain = chain
            self.combo_count = chain.kills
            self.combo_timer = COMBO_DURATION
            self.sounds.play("combo")

    def down_ufo(self, chain: KillChain | None = None, *, collision: bool = False) -> int:
        if self.ufo_x is None:
            return 0
        rect = self.ufo_image.get_rect(topleft=(round(self.ufo_x), 68))
        points = random.choice((50, 100, 150, 300))
        self.add_score(points)
        chain = chain if chain is not None else KillChain()
        self.count_chain_kill(chain, collision=collision)
        self.start_falling(self.ufo_image, rect.center, chain=chain)
        self.sounds.play("hit")
        self.ufo_x = None
        self.ufo_timer = random.uniform(15, 23)
        return points

    def update_falling_aliens(self, dt: float) -> None:
        # 新たに巻き込まれた敵は次のフレームから落下させ、連鎖を順に見せる。
        for falling in self.falling_aliens[:]:
            falling.advance(min(dt, max(0.0, FALL_DURATION - falling.age)))
            falling.smoke_timer -= dt
            while falling.smoke_timer <= 0:
                self.effects.trail(falling.center)
                falling.smoke_timer += 0.045
            falling_rect = falling.rect
            hit = False
            for alien in self.aliens[:]:
                if falling_rect.colliderect(alien.rect):
                    self.down_alien(alien, chain=falling.chain, collision=True)
                    hit = True
            if self.extra_stage is not None and self.extra_stage.boss.alive:
                if falling_rect.colliderect(self.extra_stage.boss.rect):
                    self.damage_boss(BOSS_COLLISION_DAMAGE)
                    hit = True
            if self.ufo_x is not None:
                ufo_rect = self.ufo_image.get_rect(topleft=(round(self.ufo_x), 68))
                if falling_rect.colliderect(ufo_rect):
                    self.down_ufo(chain=falling.chain, collision=True)
                    hit = True
            if hit or falling.age >= FALL_DURATION:
                self.falling_aliens.remove(falling)
                self.explosions.append(Explosion(falling.center))
                self.effects.explode(falling.center)
                self.sounds.play("explosion")

    def draw_text(
        self,
        text: str,
        position: tuple[int, int],
        color: tuple[int, int, int] = WHITE,
        *,
        centered: bool = False,
        font: PixelFont | None = None,
    ) -> None:
        image = (font or self.font).render(text, color)
        rect = image.get_rect(center=position) if centered else image.get_rect(topleft=position)
        self.screen.blit(image, rect)

    def alien_image(self, alien: Alien) -> pygame.Surface:
        if alien.beam_cannon and self.extra_stage is not None:
            return self.extra_stage.cannon_image
        if alien.special:
            images = self.resting_alien_images if self.special_resting else self.special_alien_images
        else:
            images = self.alien_images
        return images[alien.kind][self.alien_frame]

    def draw(self) -> None:
        if self.state in ("title", "debug"):
            self.screen.blit(self.background, (0, 0))
            if self.state == "title":
                self.draw_text("SPACE INVADERS", (400, 255), GREEN, centered=True, font=self.title_font)
                self.draw_text("PRESS ANY KEY", (400, 325), centered=True)
            else:
                self.draw_overlay("DEBUG START", "ENTER / SPACE TO START")
                label = "EXTRA" if self.start_phase == 4 else f"PHASE {self.start_phase}"
                self.draw_text(label, (400, 375), YELLOW, centered=True)
                phases = "1 / 2 / 3 / 4:EXTRA" if self.settings.extra_enabled else "1 / 2 / 3"
                self.draw_text(f"{phases}   PAD:LEFT / RIGHT", (400, 410), centered=True)
                self.draw_text("F2: BACK TO TITLE", (400, 445), centered=True)
            return
        background = self.extra_background if self.extra_stage is not None else self.background
        self.screen.blit(background, (0, 0))
        self.draw_text(f"SCORE {self.score:05d}", (28, 18))
        self.draw_text(f"HI {self.high_score:05d}", (315, 18), YELLOW)
        phase_label = "PHASE 0" if self.tutorial is not None else (
            "EXTRA" if self.extra_stage is not None else f"PHASE {self.wave}/{TOTAL_PHASES}"
        )
        self.draw_text(phase_label, (650, 18))
        pygame.draw.line(self.screen, (35, 55, 65), (28, 49), (772, 49))
        self.effects.draw_smoke(self.screen)
        if self.extra_stage is not None:
            self.extra_stage.draw_beams(self.screen, warnings=True)
            self.extra_stage.draw_boss(self.screen)
        for alien in self.aliens:
            self.screen.blit(self.alien_image(alien), alien.rect)
        for falling in self.falling_aliens:
            image = falling.image
            self.screen.blit(image, image.get_rect(center=falling.center))
        for explosion in self.explosions:
            self.draw_explosion(explosion)
        self.effects.draw_sparks(self.screen)
        for shield in self.shields:
            self.screen.blit(shield.image, shield.rect)
        if self.ufo_x is not None:
            self.screen.blit(self.ufo_image, (round(self.ufo_x), 68))
        if self.invincible <= 0 or int(self.invincible * 12) % 2 == 0:
            self.screen.blit(self.player_image, self.player_rect)
        for bullet in self.bullets:
            if bullet.curve_amplitude or bullet.boss_bullet:
                center = (round(bullet.x), round(bullet.y))
                pygame.draw.circle(self.screen, PINK if bullet.boss_bullet else CURVED_BULLET_COLOR, center, 5)
                pygame.draw.circle(self.screen, WHITE, center, 2)
            else:
                pygame.draw.rect(self.screen, WHITE if bullet.friendly else YELLOW, bullet.rect)
        if self.extra_stage is not None:
            self.extra_stage.draw_beams(self.screen)
        if self.bomb is not None:
            pygame.draw.ellipse(self.screen, YELLOW, self.bomb.rect)
            pygame.draw.line(
                self.screen, PINK,
                (round(self.bomb.x), round(self.bomb.y) + 9),
                (round(self.bomb.x), round(self.bomb.y) + 17), 3,
            )
        for blast in self.blasts:
            self.draw_explosion(Explosion(
                blast.center, remaining=blast.remaining * EXPLOSION_DURATION / BLAST_DURATION,
                scale=BOMB_EXPLOSION_SCALE,
            ))
        for popup in self.popups:
            self.draw_text(popup.text, popup.position, YELLOW, centered=True)
        if self.extra_stage is not None:
            # 当たり判定の6×6pxを白く示し、弾幕や機体の点滅に埋もれないよう最後に描く。
            pygame.draw.rect(self.screen, (12, 16, 24), self.player_hitbox.inflate(2, 2))
            pygame.draw.rect(self.screen, (255, 255, 255), self.player_hitbox)
        pygame.draw.line(self.screen, GREEN, (28, 575), (772, 575))
        for index in range(self.lives):
            self.screen.blit(self.heart_image, (28 + index * 20, 581))
        if self.tutorial is None or self.tutorial.step == TutorialStep.BOMB:
            self.draw_text(f"B: BOMB {self.bombs_left}", (260, 581), YELLOW, font=self.small_font)
        if self.extra_stage is not None:
            self.draw_text("SHIFT:SLOW ESC:QUIT", (520, 581), font=self.small_font)
        if self.extra_stage is not None:
            hp = self.extra_stage.boss.hp
            self.draw_text(f"BOSS HP {hp}/{BOSS_MAX_HP}", (28, 64), PINK, font=self.small_font)
            self.draw_text(self.extra_stage.boss.last_barrage_pattern, (620, 64), PINK, font=self.small_font)
            warnings = [cannon.timer for cannon in self.extra_stage.cannons.values() if cannon.state == "warning"]
            if warnings:
                self.draw_text(f"LASER {min(warnings):.1f}", (620, 86), YELLOW, font=self.small_font)
            bar = pygame.Rect(240, 88, 320, 8)
            pygame.draw.rect(self.screen, (55, 30, 65), bar)
            if hp > 0:
                pygame.draw.rect(self.screen, PINK, (bar.x, bar.y, round(bar.width * hp / BOSS_MAX_HP), bar.height))
            pygame.draw.rect(self.screen, WHITE, bar.inflate(4, 4), 1)
        if self.state == "results":
            self.screen.blit(self.background, (0, 0))
            self.draw_text("PLAYER RESULTS", (400, 70), GREEN, centered=True, font=self.title_font)
            if self.current_result:
                self.draw_text(f"YOUR POSITION  {self.result_rank} / {len(self.results)}", (400, 155), YELLOW, centered=True)
                self.draw_text(f"SCORE {self.current_result['score']:05d}   TIME {self.current_result['time']:.1f}s", (400, 190), centered=True)
            self.draw_text("RANK     SCORE       TIME", (270, 245), CYAN)
            for index, result in enumerate(self.results[:8], 1):
                color = YELLOW if index == getattr(self, "result_rank", -1) else WHITE
                self.draw_text(f"{index:>2}.       {result['score']:05d}       {result['time']:>6.1f}s", (270, 275 + index * 30), color)
            self.draw_text(f"NEXT PLAYER IN {max(0, int(self.result_timer + 0.99))}s", (400, 555), GREEN, centered=True)
            return
        if self.combo_timer > 0 and self.combo_count >= 2:
            self.draw_text(f"{self.combo_count:02d} COMBO!", (400, 68), YELLOW, centered=True, font=self.combo_font)

        if self.tutorial is not None:
            self.draw_tutorial()
        if self.state == "game_over":
            self.draw_overlay("GAME OVER", "ENTER / SPACE TO PLAY AGAIN")
            self.draw_text(f"FINAL SCORE  {self.score:05d}", (400, 375), YELLOW, centered=True)
            self.draw_text("F2: DEBUG START", (400, 407), centered=True, font=self.small_font)
        elif self.state == "victory":
            self.draw_overlay("EXTRA CLEAR!" if self.extra_stage is not None else "ALL CLEAR!", "ENTER / SPACE TO PLAY AGAIN")
            self.draw_text(f"FINAL SCORE  {self.score:05d}", (400, 375), YELLOW, centered=True)
            self.draw_text("F2: DEBUG START", (400, 407), centered=True, font=self.small_font)
        elif self.wave_timer > 0 and self.tutorial is None:
            self.draw_text("PHASE CLEAR!", (400, 300), YELLOW, centered=True)
        elif self.ready_timer > 0:
            label = "EXTRA STAGE" if self.extra_stage is not None else f"PHASE {self.wave} - {self.movement_pattern}"
            self.draw_text(label, (400, 365), YELLOW, centered=True)

    def draw_japanese(self, text: str, y: int, color: tuple[int, int, int] = WHITE) -> None:
        key = (text, color)
        if key not in self.japanese_text_cache:
            self.japanese_text_cache[key] = self.japanese_font.render(text, True, color)
        image = self.japanese_text_cache[key]
        self.screen.blit(image, image.get_rect(midtop=(400, y)))

    def draw_tutorial(self) -> None:
        tutorial = self.tutorial
        assert tutorial is not None
        step = tutorial.step
        lines = [
            (f"チュートリアル {int(step) + 1}/{len(TutorialStep)}　{STEP_TITLES[step]}", GREEN),
            (INSTRUCTIONS[step], WHITE),
            *((text, WHITE) for text in EXPLANATIONS[step]),
        ]
        if step == TutorialStep.MOVE:
            left = "完了" if tutorial.left_distance >= MOVE_DISTANCE else "未達成"
            right = "完了" if tutorial.right_distance >= MOVE_DISTANCE else "未達成"
            status = f"左への移動：{left}　右への移動：{right}"
        elif step == TutorialStep.FIRE:
            status = "発射すると次の課題へ進みます"
        elif step == TutorialStep.BOMB:
            status = f"撃墜：{tutorial.enemy_count - len(self.aliens)} / {tutorial.enemy_count} 機　外してもボムは補充されます"
        elif step == TutorialStep.DAMAGE:
            status = "ハートが1つ減りました。点滅中は無敵です" if tutorial.damage_taken else "移動せずに待つと練習用の弾が当たります"
        elif step == TutorialStep.PHASES:
            lines.append(("PHASE 1 → PHASE 2 → PHASE 3", CYAN))
            if self.settings.extra_enabled:
                lines.extend([
                    (f"PHASE {TOTAL_PHASES}を残機{EXTRA_REQUIRED_LIVES}以上でクリアすると", WHITE),
                    ("追加のEXTRAステージに進めます", WHITE),
                ])
            else:
                lines.append((f"PHASE {TOTAL_PHASES}をクリアすると本編クリアです", WHITE))
            status = "Enter／Spaceで本編へ進みます"
            if self.gamepad_name:
                status = "射撃ボタン／STARTで本編へ進みます"
        else:
            status = f"撃墜：{tutorial.enemy_count - len(self.aliens)} / {tutorial.enemy_count} 機"
        if tutorial.complete:
            status = "練習完了！　本編を開始します"
        lines.append((status, YELLOW))
        if self.gamepad_name and step in (TutorialStep.MOVE, TutorialStep.FIRE, TutorialStep.ONE_ENEMY, TutorialStep.BOMB):
            if step == TutorialStep.MOVE:
                hint = "パッド：左スティック／十字キーで移動"
            elif step == TutorialStep.BOMB:
                button = "○" if "O:BOMB" in self.gamepad_hint else "B"
                hint = f"パッド：{button}ボタンでボムを発射"
            else:
                button = "×" if "X:FIRE" in self.gamepad_hint else "A"
                hint = f"パッド：{button}ボタンで射撃"
            lines.append((hint, CYAN))
        panel = pygame.Surface((744, len(lines) * 36 + 8), pygame.SRCALPHA)
        panel.fill((4, 12, 24, 230))
        self.screen.blit(panel, (28, 52))
        for index, (text, color) in enumerate(lines):
            self.draw_japanese(text, 54 + index * 36, color)

    def draw_overlay(self, title: str, subtitle: str) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 205))
        self.screen.blit(shade, (0, 0))
        self.draw_text(title, (400, 255), GREEN, centered=True, font=self.title_font)
        self.draw_text(subtitle, (400, 325), centered=True)

    def draw_explosion(self, explosion: Explosion) -> None:
        progress = 1 - explosion.remaining / EXPLOSION_DURATION
        # 小さなキャンバスを3倍にして、閃光も炎もドット絵の輪郭に揃える。
        effect = pygame.Surface((48, 48), pygame.SRCALPHA)
        color = WHITE if progress < 0.2 else YELLOW if progress < 0.6 else (255, 110, 45)
        radius = round(4 + 14 * progress)
        pygame.draw.circle(effect, (255, 110, 35, round(65 * (1 - progress))), (24, 24), radius + 4)
        pygame.draw.circle(effect, (*color, 220), (24, 24), radius, 1)
        if progress > 0.15:
            pygame.draw.circle(effect, (255, 160, 65, 170), (24, 24), max(1, radius - 4), 1)
        # 少しずつ遅れて膨らむ火球を重ね、爆発に厚みを出す。
        for dx, dy, delay in ((0, 0, 0), (-4, 2, 0.08), (4, -3, 0.16), (1, 5, 0.24)):
            if progress < delay:
                continue
            age = (progress - delay) / (1 - delay)
            fire_radius = max(1, round(7 * (1 - age) + 2 * min(age * 6, 1)))
            center = (24 + dx, 24 + dy)
            pygame.draw.circle(effect, (245, 70, 25), center, fire_radius + 2)
            pygame.draw.circle(effect, (255, 160, 40), center, fire_radius)
            pygame.draw.circle(effect, (255, 240, 150), center, max(1, fire_radius - 3))
        if progress < 0.18:
            pygame.draw.line(effect, WHITE, (10, 24), (38, 24), 1)
            pygame.draw.line(effect, WHITE, (24, 10), (24, 38), 1)
            pygame.draw.rect(effect, WHITE, (21, 21, 6, 6))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)):
            position = (round(24 + dx * radius), round(24 + dy * radius), 2, 2)
            pygame.draw.rect(effect, color, position)
        effect.set_alpha(round(255 * (1 - progress)))
        size = round(144 * explosion.scale)
        effect = pygame.transform.scale(effect, (size, size))
        self.screen.blit(effect, (explosion.center[0] - size // 2, explosion.center[1] - size // 2))


def main() -> None:
    pygame.display.init()
    sounds = None
    gamepad = None
    try:
        display = PixelDisplay((WIDTH, HEIGHT))
        pygame.display.set_caption("Space Invaders")
        clock = pygame.time.Clock()
        sounds = SoundEffects()
        gamepad = Gamepad()
        game = Game(display.canvas, sounds=sounds)
        running = True
        while running:
            # ウィンドウ移動などによる長い停止後にも、弾が敵を飛び越えないようにする。
            dt = min(clock.tick(FPS) / 1000.0, 1 / 30)
            for event in pygame.event.get():
                if display.handle_event(event):
                    continue
                if not game.handle_event(event):
                    running = False
            if not running:
                break
            pad_input = gamepad.poll()
            game.gamepad_name = gamepad.name
            game.gamepad_hint = gamepad.hint
            game.handle_gamepad(pad_input)
            game.update(dt, pygame.key.get_pressed(), pad_input)
            game.draw()
            display.present()
    finally:
        if gamepad is not None:
            gamepad.close()
        if sounds is not None:
            sounds.close()
        pygame.quit()


if __name__ == "__main__":
    main()
