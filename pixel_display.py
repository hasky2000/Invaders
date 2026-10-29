"""内部解像度を固定し、完成したフレームだけを最近傍補間で拡大する。"""

import math

import pygame


def initial_window_size(logical_size: tuple[int, int], desktop_size: tuple[int, int]) -> tuple[int, int]:
    # タイトルバーなどの余裕を取り、最大2倍まで0.5倍刻みで画面に収める。
    width, height = logical_size
    fit = min(2.0, max(1, desktop_size[0] - 64) / width, max(1, desktop_size[1] - 96) / height)
    scale = math.floor(fit * 2) / 2 if fit >= 1 else fit
    return max(1, round(width * scale)), max(1, round(height * scale))


def scaled_viewport(logical_size: tuple[int, int], window_size: tuple[int, int]) -> pygame.Rect:
    scale = min(window_size[0] / logical_size[0], window_size[1] / logical_size[1])
    width = max(1, int(logical_size[0] * scale))
    height = max(1, int(logical_size[1] * scale))
    return pygame.Rect((window_size[0] - width) // 2, (window_size[1] - height) // 2, width, height)


class PixelDisplay:
    def __init__(self, logical_size: tuple[int, int], *, window_size: tuple[int, int] | None = None):
        if window_size is None:
            window_size = initial_window_size(logical_size, pygame.display.get_desktop_sizes()[0])
        self.window = pygame.display.set_mode(window_size, pygame.RESIZABLE)
        self.canvas = pygame.Surface(logical_size).convert()
        self.windowed_size = window_size
        self.fullscreen = False
        self.scaled_frame: pygame.Surface | None = None

    def handle_event(self, event: pygame.event.Event) -> bool:
        """表示側で処理したイベントはTrueを返す。ゲームの状態は変えない。"""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
            if not getattr(event, "repeat", False):
                self.toggle_fullscreen()
            return True
        if event.type == pygame.VIDEORESIZE:
            if not self.fullscreen:
                self.windowed_size = (max(1, event.w), max(1, event.h))
                self.window = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
            return True
        return False

    def toggle_fullscreen(self) -> None:
        if self.fullscreen:
            self.window = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        else:
            self.windowed_size = self.window.get_size()
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.fullscreen = not self.fullscreen

    def present(self) -> None:
        viewport = scaled_viewport(self.canvas.get_size(), self.window.get_size())
        if self.scaled_frame is None or self.scaled_frame.get_size() != viewport.size:
            self.scaled_frame = pygame.Surface(viewport.size).convert()
        # smoothscaleを使わず、元のピクセルの色をそのまま拡大する。
        pygame.transform.scale(self.canvas, viewport.size, self.scaled_frame)
        self.window.fill((0, 0, 0))
        self.window.blit(self.scaled_frame, viewport)
        pygame.display.flip()
