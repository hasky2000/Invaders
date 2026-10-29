"""外部素材を使わない仮のレトロSE。音声デバイスがなくてもゲームは動作する。"""

import importlib
import math
import random
from array import array
from dataclasses import dataclass

import pygame

@dataclass(frozen=True)
class SoundSpec:
    duration: float
    start: float
    end: float
    volume: float
    noise: float = 0.0


SOUNDS = {
    "shoot": SoundSpec(0.07, 1100, 480, 0.11),
    "enemy_shot": SoundSpec(0.09, 360, 180, 0.06),
    "beam_charge": SoundSpec(2.0, 300, 1600, 0.12),
    "beam_fire": SoundSpec(0.45, 130, 55, 0.2, 0.4),
    "bomb_launch": SoundSpec(0.2, 140, 420, 0.12),
    "hit": SoundSpec(0.12, 650, 130, 0.13, 0.25),
    "explosion": SoundSpec(0.28, 150, 35, 0.2, 0.75),
    "bomb_explosion": SoundSpec(0.5, 100, 25, 0.25, 0.85),
    "player_hit": SoundSpec(0.35, 260, 45, 0.22, 0.65),
    "combo": SoundSpec(0.16, 650, 1500, 0.14),
    "clear": SoundSpec(0.5, 520, 1040, 0.15),
    "victory": SoundSpec(0.75, 520, 1560, 0.18),
    "game_over": SoundSpec(0.5, 320, 70, 0.16),
}


def synthesize(spec: SoundSpec, sample_rate: int, channels: int) -> bytes:
    samples = array("h")
    noise = random.Random(7)  # 演出がゲーム本体の乱数に影響しないようにする。
    phase = 0.0
    length = round(sample_rate * spec.duration)
    for index in range(length):
        progress = index / length
        frequency = spec.start + (spec.end - spec.start) * progress
        phase += math.tau * frequency / sample_rate
        square = 1.0 if math.sin(phase) >= 0 else -1.0
        value = square * (1 - spec.noise) + noise.uniform(-1, 1) * spec.noise
        envelope = min(1.0, index / (sample_rate * 0.004)) * (1 - progress) ** 2
        sample = round(value * envelope * spec.volume * 32767)
        samples.extend([sample] * channels)
    return samples.tobytes()


class SoundEffects:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = False
        self.muted = False
        self.mixer = None
        self.sounds: dict[str, object] = {}
        self.last_played: dict[str, int] = {}
        if not enabled:
            return
        try:
            mixer = importlib.import_module("pygame.mixer")
            if mixer.get_init() is None:
                mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            sample_rate, sample_format, channels = mixer.get_init()
            if sample_format != -16:
                return
            mixer.set_num_channels(12)
            self.sounds = {
                name: mixer.Sound(buffer=synthesize(spec, sample_rate, channels))
                for name, spec in SOUNDS.items()
            }
            self.mixer = mixer
            self.enabled = True
        except (ImportError, pygame.error, NotImplementedError):
            # 音声デバイスがない環境でも、ゲーム自体は続行できる。
            return

    def play(self, name: str) -> None:
        if not self.enabled or self.muted:
            return
        now = pygame.time.get_ticks()
        # 同時撃墜時の音割れを防ぎ、短いSEをまとめる。
        if now - self.last_played.get(name, -1000) < 65:
            return
        self.last_played[name] = now
        important = name in ("beam_charge", "beam_fire", "bomb_explosion", "player_hit", "victory", "game_over")
        channel = self.mixer.find_channel(force=important)
        if channel is not None:
            channel.play(self.sounds[name])

    def toggle_mute(self) -> None:
        self.muted = not self.muted
        if self.enabled and self.muted:
            self.mixer.stop()

    def pause(self, paused: bool) -> None:
        if self.enabled:
            self.mixer.pause() if paused else self.mixer.unpause()

    def close(self) -> None:
        if self.enabled:
            self.mixer.stop()
            self.mixer.quit()
            self.enabled = False
