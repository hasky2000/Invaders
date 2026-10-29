"""EXTRAのボス・取り巻きの移動と、予告付きビーム。ゲーム進行はmain側で扱う。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from main import Alien


EXTRA_REQUIRED_LIVES = 3
EXTRA_ESCORT_COUNT = 10
BEAM_CANNON_COLUMNS = (0, 5)
BOSS_MAX_HP = 240
BOSS_BULLET_SPEED = 115.2
BOSS_BOMB_DAMAGE = 15
BOSS_COLLISION_DAMAGE = 5
BEAM_WARNING_TIME = 2.0
BEAM_FIRE_TIME = 0.45
BEAM_COOLDOWN = 4.5
BEAM_WIDTH = 48
BEAM_BOTTOM = 575
BEAM_LENGTH = 1200
BEAM_EXTENSION_SPEED = 1800
EXTRA_BULLET_LIMIT = 221
BARRAGE_VOLLEYS_PER_PATTERN = 12
BARRAGE_DENSITY_MULTIPLIER = 0.918


@dataclass(frozen=True)
class BarrageShot:
    offset: tuple[float, float]
    velocity: tuple[float, float]


@dataclass
class Boss:
    rect: pygame.Rect = field(default_factory=lambda: pygame.Rect(320, 138, 160, 128))
    hp: int = BOSS_MAX_HP
    hit_flash: float = 0.0
    shot_timer: float = 1.2
    volley_index: int = 0
    last_barrage_pattern: str = "ROSETTE"

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def barrage_pattern(self) -> str:
        return ("ROSETTE", "CROSS", "HELIX")[(self.volley_index // BARRAGE_VOLLEYS_PER_PATTERN) % 3]

    @property
    def barrage_interval(self) -> float:
        base_interval = {"ROSETTE": 0.42, "CROSS": 0.52, "HELIX": 0.14}[self.barrage_pattern]
        return base_interval / BARRAGE_DENSITY_MULTIPLIER

    def barrage_shots(self, speed: float) -> list[BarrageShot]:
        """左右の砲口から、逆回転・交差・高速連射を組み合わせた等速弾幕を作る。"""
        step = self.volley_index % BARRAGE_VOLLEYS_PER_PATTERN
        shots = []
        for side in (-1, 1):
            if self.barrage_pattern == "ROSETTE":
                # 2つの円を逆向きに回し、重なる花びらと動く隙間を作る。
                offset = (side * 32, 10)
                angles = [math.tau * index / 16 + side * (step * 0.19 + math.pi / 32) for index in range(16)]
            elif self.barrage_pattern == "CROSS":
                # 左右の扇を内側へ向けて揺らし、斜めに交差する格子を作る。
                offset = (side * 52, 14)
                center = math.pi / 2 + side * (0.30 + math.sin(step * 0.5) * 0.22)
                angles = [center + (index - 8) * 0.095 for index in range(17)]
            else:
                # 回転方向の異なる8本の腕を短い間隔で重ね、二重の螺旋にする。
                offset = (side * 24, 10)
                angles = [math.tau * index / 8 + side * (step * 0.28 + math.pi / 16) for index in range(8)]
            shots.extend(BarrageShot(offset, (math.cos(angle) * speed, math.sin(angle) * speed)) for angle in angles)
        return shots


@dataclass
class BeamCannon:
    timer: float
    state: str = "cooldown"
    origin: tuple[int, int] = (0, 0)
    direction: tuple[float, float] = (0.0, 1.0)

    @property
    def length(self) -> float:
        if self.state == "warning":
            return BEAM_LENGTH
        if self.state == "firing":
            return min(BEAM_LENGTH, max(0.0, BEAM_FIRE_TIME - self.timer) * BEAM_EXTENSION_SPEED)
        return 0.0

    def aim(self, target: tuple[int, int]) -> None:
        vector = pygame.Vector2(target) - self.origin
        self.direction = tuple(vector.normalize()) if vector.length_squared() else (0.0, 1.0)

    def polygon(self, width: float = BEAM_WIDTH) -> list[tuple[float, float]]:
        direction = pygame.Vector2(self.direction)
        side = pygame.Vector2(-direction.y, direction.x) * width / 2
        start = pygame.Vector2(self.origin)
        end = start + direction * self.length
        return [tuple(start + side), tuple(end + side), tuple(end - side), tuple(start - side)]

    def hits(self, hitbox: pygame.Rect) -> bool:
        """斜めのビームと矩形を分離軸で判定し、外接矩形の空白には当てない。"""
        if self.state != "firing" or self.length <= 0:
            return False
        direction = pygame.Vector2(self.direction)
        side = pygame.Vector2(-direction.y, direction.x)
        center = pygame.Vector2(self.origin) + direction * self.length / 2
        delta = pygame.Vector2(hitbox.x + hitbox.width / 2, hitbox.y + hitbox.height / 2) - center
        for axis in (pygame.Vector2(1, 0), pygame.Vector2(0, 1), direction, side):
            beam_radius = abs(axis.dot(direction)) * self.length / 2 + abs(axis.dot(side)) * BEAM_WIDTH / 2
            player_radius = abs(axis.x) * hitbox.width / 2 + abs(axis.y) * hitbox.height / 2
            if abs(delta.dot(axis)) >= beam_radius + player_radius - 1e-9:
                return False
        return True

    def advance(self, dt: float, origin: tuple[int, int], target: tuple[int, int]) -> str | None:
        """予告開始時だけ照準を決め、予告・発射が終わるまで固定する。"""
        self.timer -= dt
        if self.timer > 1e-9:
            return None
        if self.state == "cooldown":
            self.state = "warning"
            self.origin = origin
            self.aim(target)
            self.timer = BEAM_WARNING_TIME
            return "beam_charge"
        if self.state == "warning":
            self.state = "firing"
            self.timer = BEAM_FIRE_TIME
            return "beam_fire"
        self.state = "cooldown"
        self.timer = BEAM_COOLDOWN
        return None


class ExtraStage:
    def __init__(self) -> None:
        self.boss = Boss()
        self.elapsed = 0.0
        # 2門の予告・発射タイミングをずらし、同時に退路を塞がないようにする。
        self.cannons = {
            column: BeamCannon(timer=3.0 + index * 2.7)
            for index, column in enumerate(BEAM_CANNON_COLUMNS)
        }
        self.boss_image = self.make_boss_image()
        self.boss_flash_image = self.boss_image.copy()
        self.boss_flash_image.fill((100, 100, 100), special_flags=pygame.BLEND_RGB_ADD)
        self.cannon_image = self.make_cannon_image()

    def escort_center(self, column: int) -> tuple[int, int]:
        angle = math.tau * column / EXTRA_ESCORT_COUNT + self.elapsed * 0.22
        return (
            self.boss.rect.centerx + round(math.cos(angle) * 220),
            self.boss.rect.centery + round(math.sin(angle) * 92),
        )

    def advance(self, dt: float, aliens: list[Alien], target: tuple[int, int]) -> list[str]:
        if not self.boss.alive:
            return []
        self.elapsed += dt
        self.boss.rect.centerx = 400 + round(math.sin(self.elapsed * 0.55) * 36)
        self.boss.hit_flash = max(0.0, self.boss.hit_flash - dt)
        alive_columns = {alien.column for alien in aliens}
        self.cannons = {column: cannon for column, cannon in self.cannons.items() if column in alive_columns}
        sounds = []
        for alien in aliens:
            cannon = self.cannons.get(alien.column)
            # 予告・発射中は砲台を止め、見た目と判定位置を一致させる。
            if cannon is None or cannon.state == "cooldown":
                alien.rect.center = self.escort_center(alien.column)
            if cannon is not None:
                sound = cannon.advance(dt, alien.rect.midbottom, target)
                if sound is not None:
                    sounds.append(sound)
        return sounds

    def remove_escort(self, column: int) -> None:
        # 発射元を倒すと、予告中でも発射中でもビームが消える。
        self.cannons.pop(column, None)

    def hits_player(self, hitbox: pygame.Rect) -> bool:
        return any(cannon.hits(hitbox) for cannon in self.cannons.values())

    def draw_boss(self, screen: pygame.Surface) -> None:
        if self.boss.alive:
            image = self.boss_flash_image if self.boss.hit_flash > 0 else self.boss_image
            screen.blit(image, self.boss.rect)

    def draw_beams(self, screen: pygame.Surface, *, warnings: bool = False) -> None:
        """予告は機体・弾の下、発射中のビームはその上に描くために分ける。"""
        layer = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        layer.set_clip(pygame.Rect(0, 50, screen.get_width(), BEAM_BOTTOM - 50))
        for cannon in self.cannons.values():
            if cannon.state != ("warning" if warnings else "firing"):
                continue
            if cannon.state == "warning":
                # 赤い銀河にも埋もれない、明るい赤の半透明帯にする。
                pygame.draw.polygon(layer, (255, 100, 110, 110), cannon.polygon())
            elif cannon.length > 0:
                pygame.draw.polygon(layer, (255, 35, 70, 65), cannon.polygon(BEAM_WIDTH + 18))
                pygame.draw.polygon(layer, (255, 65, 95, 235), cannon.polygon())
                pygame.draw.polygon(layer, (255, 210, 220, 255), cannon.polygon(BEAM_WIDTH - 14))
                pygame.draw.polygon(layer, (255, 255, 255, 255), cannon.polygon(BEAM_WIDTH - 30))
        screen.blit(layer, (0, 0))

    @staticmethod
    def make_boss_image() -> pygame.Surface:
        """楔形の灰色船体、段状の甲板、艦橋と2つの球形センサーを描く。"""
        image = pygame.Surface((40, 32), pygame.SRCALPHA)
        hull = [(1, 6), (38, 6), (20, 31)]
        pygame.draw.polygon(image, (125, 140, 155), hull)
        pygame.draw.polygon(image, (175, 185, 195), [(1, 6), (20, 7), (20, 31)])
        pygame.draw.polygon(image, (145, 158, 172), [(20, 7), (38, 6), (20, 31)])
        pygame.draw.lines(image, (210, 220, 225), False, [(1, 6), (20, 31), (38, 6)], 1)
        # 装甲の継ぎ目と、中央に積み重なる上部構造。
        pygame.draw.polygon(image, (90, 105, 125), [(7, 9), (32, 9), (20, 27)])
        pygame.draw.polygon(image, (185, 195, 205), [(9, 9), (30, 9), (20, 25)])
        pygame.draw.polygon(image, (130, 145, 162), [(12, 10), (27, 10), (20, 22)])
        for y, width in ((10, 18), (13, 12), (16, 8)):
            pygame.draw.rect(image, (100, 115, 135), (20 - width // 2, y, width, 3))
            pygame.draw.line(image, (215, 220, 225), (20 - width // 2, y), (19 + width // 2, y))
        pygame.draw.line(image, (225, 230, 235), (20, 17), (20, 28))
        for side in (-1, 1):
            for y, distance in ((9, 14), (13, 10), (18, 6)):
                x = 20 + side * distance
                pygame.draw.rect(image, (70, 85, 105), (x - 1, y, 2, 2))
                pygame.draw.rect(image, (225, 230, 225), (x - 1, y, 2, 1))
            pygame.draw.circle(image, (210, 220, 230), (20 + side * 6, 2), 2)
            pygame.draw.line(image, (110, 125, 145), (20 + side * 6, 3), (20 + side * 6, 5))
        # 船尾のエンジンと、横に長い艦橋。
        for x in (6, 13, 24, 31):
            pygame.draw.rect(image, (105, 175, 235), (x, 5, 3, 2))
            pygame.draw.line(image, (200, 235, 255), (x, 5), (x + 2, 5))
        pygame.draw.rect(image, (90, 105, 125), (17, 4, 6, 6))
        pygame.draw.rect(image, (185, 200, 215), (10, 4, 20, 3))
        pygame.draw.line(image, (225, 235, 240), (10, 4), (29, 4))
        pygame.draw.line(image, (55, 85, 110), (12, 6), (27, 6))
        return pygame.transform.scale(image, (160, 128))

    @staticmethod
    def make_cannon_image() -> pygame.Surface:
        image = pygame.Surface((10, 12), pygame.SRCALPHA)
        pygame.draw.rect(image, (185, 75, 95), (1, 1, 8, 7))
        pygame.draw.rect(image, (255, 175, 100), (2, 2, 6, 3))
        pygame.draw.rect(image, (120, 120, 160), (1, 6, 8, 5))
        pygame.draw.rect(image, (245, 235, 240), (2, 10, 6, 2))
        pygame.draw.rect(image, (255, 65, 90), (4, 7, 2, 4))
        return pygame.transform.scale(image, (30, 36))
