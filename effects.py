"""煙と火花の描画。すべて演出用で、当たり判定には関与しない。"""

import math
import random
from dataclasses import dataclass

import pygame


MAX_PARTICLES = 1800


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    lifetime: float
    remaining: float
    radius: float
    color: tuple[int, int, int]
    smoke: bool
    debris: bool = False
    delay: float = 0.0

    def advance(self, dt: float) -> None:
        if self.delay > 0:
            waiting = min(dt, self.delay)
            self.delay -= waiting
            dt -= waiting
        self.remaining -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= math.exp(-dt * (1.4 if self.smoke else 0.8))
        self.vy += (-12 if self.smoke else 110) * dt


class Effects:
    def __init__(self) -> None:
        self.particles: list[Particle] = []

    def add(
        self, center: tuple[int, int], velocity: tuple[float, float],
        lifetime: float, radius: float, color: tuple[int, int, int], *, smoke: bool,
        debris: bool = False, delay: float = 0.0,
    ) -> None:
        if len(self.particles) >= MAX_PARTICLES:
            return
        self.particles.append(Particle(
            center[0], center[1], velocity[0], velocity[1],
            lifetime, lifetime, radius, color, smoke, debris, delay,
        ))

    def trail(self, center: tuple[int, int]) -> None:
        self.add(
            center, (random.uniform(-14, 14), random.uniform(-35, -18)),
            random.uniform(0.65, 1.0), random.uniform(3, 5), (110, 108, 115), smoke=True,
        )
        self.add(
            center, (random.uniform(-25, 25), random.uniform(-55, -20)),
            0.25, 3, (255, 150, 50), smoke=False,
        )

    def explode(self, center: tuple[int, int], *, scale: float = 1.0) -> None:
        for _ in range(round(16 * scale)):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(20, 55) * scale
            self.add(
                center, (math.cos(angle) * speed, math.sin(angle) * speed - 25),
                random.uniform(0.8, 1.3), random.uniform(4, 8) * math.sqrt(scale),
                random.choice(((100, 100, 115), (140, 125, 110), (80, 85, 100))), smoke=True,
            )
        for index in range(round(36 * scale)):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(90, 255) * scale
            self.add(
                center, (math.cos(angle) * speed, math.sin(angle) * speed),
                random.uniform(0.35, 0.8), random.uniform(2, 4),
                random.choice(((255, 245, 195), (255, 180, 60), (255, 100, 35))), smoke=False,
                delay=(index % 3) * 0.055,
            )
        for _ in range(round(8 * scale)):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(45, 130) * scale
            self.add(
                center, (math.cos(angle) * speed, math.sin(angle) * speed - 30),
                random.uniform(0.6, 1.0), random.uniform(3, 6),
                random.choice(((165, 140, 110), (210, 160, 85), (110, 120, 140))),
                smoke=False, debris=True,
            )

    def update(self, dt: float) -> None:
        for particle in self.particles:
            particle.advance(dt)
        self.particles = [particle for particle in self.particles if particle.remaining > 0]

    def draw_smoke(self, screen: pygame.Surface) -> None:
        for particle in self.particles:
            if not particle.smoke or particle.delay > 0:
                continue
            progress = 1 - particle.remaining / particle.lifetime
            radius = round(particle.radius + progress * 15)
            puff = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            color = (*particle.color, round(150 * (1 - progress)))
            pygame.draw.circle(puff, color, (radius + 1, radius + 1), radius)
            screen.blit(puff, (round(particle.x) - radius - 1, round(particle.y) - radius - 1))

    def draw_sparks(self, screen: pygame.Surface) -> None:
        layer = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        for particle in self.particles:
            if particle.smoke or particle.delay > 0:
                continue
            alpha = round(255 * particle.remaining / particle.lifetime)
            size = max(1, round(particle.radius))
            center = (round(particle.x), round(particle.y))
            tail = (round(particle.x - particle.vx * 0.035), round(particle.y - particle.vy * 0.035))
            if particle.debris:
                pygame.draw.rect(layer, (*particle.color, alpha), (*center, size, size))
                pygame.draw.rect(layer, (255, 200, 100, alpha), (*center, 2, 2))
            else:
                pygame.draw.line(layer, (*particle.color, alpha), center, tail, size)
        screen.blit(layer, (0, 0))
