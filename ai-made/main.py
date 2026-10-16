"""800 x 600 のクラシックなインベーダーゲーム。pygame のみで動作する。"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

from pixel_font import PixelFont


WIDTH, HEIGHT = 800, 600
FPS = 60
BACKGROUND = (8, 10, 18)
WHITE = (225, 235, 240)
GREEN = (100, 240, 140)
CYAN = (100, 215, 245)
PINK = (245, 110, 150)
YELLOW = (250, 220, 120)
PLAYER_SPEED = 320
PLAYER_Y = 540
SHOT_COOLDOWN = 0.26

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

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(round(self.x) - 2, round(self.y) - 6, 4, 12)


@dataclass
class Alien:
    rect: pygame.Rect
    row: int
    column: int

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
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.font = PixelFont(2)
        self.small_font = PixelFont(2)
        self.title_font = PixelFont(6)
        self.player_image = pixel_sprite(PLAYER_PATTERN, GREEN)
        self.alien_images = [
            [pixel_sprite(frame, (CYAN, GREEN, PINK)[kind]) for frame in frames]
            for kind, frames in enumerate(ALIEN_PATTERNS)
        ]
        self.ufo_image = pixel_sprite(UFO_PATTERN, PINK)
        self.high_score = 0  # 今回の起動中のハイスコア。
        self.reset()
        self.state = "title"

    def reset(self) -> None:
        self.score = 0
        self.lives = 3
        self.wave = 1
        self.player_x = WIDTH / 2
        self.shot_timer = 0.0
        self.invincible = 0.0
        self.bullets: list[Bullet] = []
        self.popups: list[Popup] = []
        self.shields = [Shield(x) for x in (145, 315, 485, 655)]
        self.state = "playing"
        self.prepare_wave()

    @property
    def player_rect(self) -> pygame.Rect:
        rect = self.player_image.get_rect()
        rect.midbottom = (round(self.player_x), PLAYER_Y + 21)
        return rect

    def prepare_wave(self) -> None:
        # 高いウェーブでも出現時に防壁に重ならないよう、開始位置には上限を設ける。
        start_y = 112 + min(self.wave - 1, 5) * 12
        self.aliens = [
            Alien(pygame.Rect(118 + column * 52, start_y + row * 40, 24, 24), row, column)
            for row in range(5)
            for column in range(11)
        ]
        self.direction = 1
        self.alien_timer = 0.0
        self.alien_frame = 0
        self.enemy_shot_timer = 1.0
        self.ufo_x: float | None = None
        self.ufo_timer = random.uniform(15, 23)
        self.bullets.clear()
        self.wave_timer = 0.0
        self.ready_timer = 1.2

    def add_score(self, points: int) -> None:
        self.score += points
        self.high_score = max(self.high_score, self.score)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """False を返した場合は、メインループを終了する。"""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.WINDOWFOCUSLOST and self.state == "playing":
            self.state = "paused"
        if event.type != pygame.KEYDOWN:
            return True
        if event.key == pygame.K_ESCAPE:
            return False
        if self.state in ("title", "game_over") and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.reset()
        elif event.key == pygame.K_p and self.state in ("playing", "paused"):
            self.state = "paused" if self.state == "playing" else "playing"
        return True

    def update(self, dt: float, keys: pygame.key.ScancodeWrapper) -> None:
        if self.state != "playing":
            return
        for popup in self.popups[:]:
            popup.remaining -= dt
            if popup.remaining <= 0:
                self.popups.remove(popup)
        if self.wave_timer > 0:
            self.wave_timer -= dt
            if self.wave_timer <= 0:
                self.wave += 1
                self.prepare_wave()
            return
        if self.ready_timer > 0:
            self.ready_timer -= dt
            return

        self.invincible = max(0.0, self.invincible - dt)
        self.shot_timer = max(0.0, self.shot_timer - dt)
        movement = int(keys[pygame.K_RIGHT] or keys[pygame.K_d]) - int(keys[pygame.K_LEFT] or keys[pygame.K_a])
        half_width = self.player_image.get_width() / 2
        self.player_x = max(28 + half_width, min(WIDTH - 28 - half_width, self.player_x + movement * PLAYER_SPEED * dt))
        if keys[pygame.K_SPACE]:
            self.fire()

        self.move_aliens(dt)
        if self.state != "playing":
            return
        self.update_enemy_fire(dt)
        self.update_ufo(dt)
        self.update_bullets(dt)
        if self.state == "playing" and not self.aliens:
            self.bullets.clear()
            self.wave_timer = 1.7

    def fire(self) -> None:
        if self.shot_timer > 0 or sum(bullet.friendly for bullet in self.bullets) >= 2:
            return
        self.bullets.append(Bullet(self.player_x, self.player_rect.top - 8, -510, True))
        self.shot_timer = SHOT_COOLDOWN

    def move_aliens(self, dt: float) -> None:
        # 数が減るほど移動間隔が短くなり、最後の一体まで緊張感を保つ。
        interval = max(0.065, 0.55 - (55 - len(self.aliens)) * 0.0085 - (self.wave - 1) * 0.035)
        self.alien_timer += dt
        if self.alien_timer < interval or not self.aliens:
            return
        self.alien_timer -= interval
        self.alien_frame = 1 - self.alien_frame
        step = 12 * self.direction
        at_edge = any(alien.rect.left + step < 28 or alien.rect.right + step > WIDTH - 28 for alien in self.aliens)
        if at_edge:
            self.direction *= -1
        for alien in self.aliens:
            alien.rect.move_ip(0 if at_edge else step, 22 if at_edge else 0)
            for shield in self.shields:
                shield.crush(alien.rect)
        if any(alien.rect.bottom >= self.player_rect.top for alien in self.aliens):
            self.state = "game_over"

    def update_enemy_fire(self, dt: float) -> None:
        self.enemy_shot_timer -= dt
        if self.enemy_shot_timer > 0 or not self.aliens:
            return
        self.enemy_shot_timer = random.uniform(0.55, 1.15) / (1 + (self.wave - 1) * 0.08)
        if sum(not bullet.friendly for bullet in self.bullets) >= 4:
            return
        # 各列の最下段からのみ発射し、味方の敵を弾が貫通する見た目を防ぐ。
        front_line: dict[int, Alien] = {}
        for alien in self.aliens:
            if alien.column not in front_line or alien.rect.bottom > front_line[alien.column].rect.bottom:
                front_line[alien.column] = alien
        shooter = random.choice(list(front_line.values()))
        speed = min(340, 210 + self.wave * 12)
        self.bullets.append(Bullet(shooter.rect.centerx, shooter.rect.bottom + 8, speed, False))

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
            bullet.y += bullet.velocity * dt

        for bullet in self.bullets[:]:
            if bullet not in self.bullets:
                continue
            if bullet.rect.bottom < 55 or bullet.rect.top > 576:
                self.bullets.remove(bullet)
                continue
            if any(shield.hit(bullet) for shield in self.shields):
                self.bullets.remove(bullet)
                continue
            if bullet.friendly:
                self.resolve_player_bullet(bullet)
            elif bullet.rect.colliderect(self.player_rect):
                self.bullets.remove(bullet)
                if self.invincible <= 0:
                    self.lives -= 1
                    self.invincible = 1.8
                    self.popups.append(Popup(self.player_rect.center, "*"))
                    if self.lives <= 0:
                        self.state = "game_over"
                        break

    def resolve_player_bullet(self, bullet: Bullet) -> None:
        for alien in self.aliens:
            if bullet.rect.colliderect(alien.rect):
                self.aliens.remove(alien)
                self.bullets.remove(bullet)
                self.add_score(alien.points)
                self.popups.append(Popup(alien.rect.center, "+"))
                return
        if self.ufo_x is not None:
            ufo_rect = self.ufo_image.get_rect(topleft=(round(self.ufo_x), 68))
            if bullet.rect.colliderect(ufo_rect):
                points = random.choice((50, 100, 150, 300))
                self.add_score(points)
                self.popups.append(Popup(ufo_rect.center, str(points)))
                self.ufo_x = None
                self.ufo_timer = random.uniform(15, 23)
                self.bullets.remove(bullet)

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

    def draw(self) -> None:
        self.screen.fill(BACKGROUND)
        self.draw_text(f"SCORE {self.score:05d}", (28, 18))
        self.draw_text(f"HI {self.high_score:05d}", (315, 18), YELLOW)
        self.draw_text(f"WAVE {self.wave:02d}", (650, 18))
        pygame.draw.line(self.screen, (35, 55, 65), (28, 49), (772, 49))
        for alien in self.aliens:
            self.screen.blit(self.alien_images[alien.kind][self.alien_frame], alien.rect)
        for shield in self.shields:
            self.screen.blit(shield.image, shield.rect)
        if self.ufo_x is not None:
            self.screen.blit(self.ufo_image, (round(self.ufo_x), 68))
        if self.invincible <= 0 or int(self.invincible * 12) % 2 == 0:
            self.screen.blit(self.player_image, self.player_rect)
        for bullet in self.bullets:
            pygame.draw.rect(self.screen, WHITE if bullet.friendly else YELLOW, bullet.rect)
        for popup in self.popups:
            self.draw_text(popup.text, popup.position, YELLOW, centered=True)
        pygame.draw.line(self.screen, GREEN, (28, 575), (772, 575))
        self.draw_text(f"LIVES {self.lives}", (28, 581), GREEN, font=self.small_font)
        self.draw_text("P: PAUSE  ESC: QUIT", (556, 581), font=self.small_font)

        if self.state == "title":
            self.draw_overlay("SPACE INVADERS", "ENTER / SPACE TO START")
            self.draw_text("ARROWS / A D: MOVE     SPACE: FIRE", (400, 370), GREEN, centered=True, font=self.small_font)
            self.draw_text("30 / 20 / 10 PTS     UFO: 50-300 PTS", (400, 402), centered=True, font=self.small_font)
        elif self.state == "paused":
            self.draw_overlay("PAUSED", "PRESS P TO RESUME")
        elif self.state == "game_over":
            self.draw_overlay("GAME OVER", "ENTER / SPACE TO PLAY AGAIN")
            self.draw_text(f"FINAL SCORE  {self.score:05d}", (400, 375), YELLOW, centered=True)
        elif self.wave_timer > 0:
            self.draw_text("WAVE CLEAR!", (400, 300), YELLOW, centered=True)
        elif self.ready_timer > 0:
            self.draw_text(f"WAVE {self.wave:02d} - READY", (400, 365), YELLOW, centered=True)

    def draw_overlay(self, title: str, subtitle: str) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 205))
        self.screen.blit(shade, (0, 0))
        self.draw_text(title, (400, 255), GREEN, centered=True, font=self.title_font)
        self.draw_text(subtitle, (400, 325), centered=True)


def main() -> None:
    pygame.display.init()
    try:
        screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Space Invaders")
        clock = pygame.time.Clock()
        game = Game(screen)
        running = True
        while running:
            # ウィンドウ移動などによる長い停止後にも、弾が敵を飛び越えないようにする。
            dt = min(clock.tick(FPS) / 1000.0, 1 / 30)
            for event in pygame.event.get():
                if not game.handle_event(event):
                    running = False
            if not running:
                break
            game.update(dt, pygame.key.get_pressed())
            game.draw()
            pygame.display.flip()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
