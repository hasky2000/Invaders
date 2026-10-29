"""表示サイズを変えても、内部解像度・ピクセルの色・ゲーム進行を維持する。"""

import math
import os
import unittest
from collections import defaultdict

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from main import Game
from pixel_display import PixelDisplay, initial_window_size, scaled_viewport


class PixelDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.display = PixelDisplay((800, 600), window_size=(1600, 1200))

    def test_initial_enlargement_fits_desktop(self):
        self.assertEqual(initial_window_size((800, 600), (1536, 1024)), (1200, 900))
        self.assertEqual(initial_window_size((800, 600), (2560, 1440)), (1600, 1200))
        self.assertEqual(initial_window_size((800, 600), (1024, 768)), (800, 600))

    def test_double_size_repeats_pixels_without_blending(self):
        canvas = self.display.canvas
        canvas.fill((0, 0, 0))
        color = (213, 57, 89)
        canvas.set_at((23, 37), color)
        self.display.present()
        for point in ((46, 74), (47, 74), (46, 75), (47, 75)):
            self.assertEqual(tuple(self.display.window.get_at(point))[:3], color)
        self.assertEqual(tuple(self.display.window.get_at((45, 74)))[:3], (0, 0, 0))
        self.assertEqual(canvas.get_size(), (800, 600))

    def test_non_integer_enlargement_preserves_original_palette(self):
        display = PixelDisplay((2, 2), window_size=(5, 5))
        colors = {(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)}
        for point, color in zip(((0, 0), (1, 0), (0, 1), (1, 1)), sorted(colors)):
            display.canvas.set_at(point, color)
        display.present()
        shown = {tuple(display.window.get_at((x, y)))[:3] for x in range(5) for y in range(5)}
        self.assertEqual(shown, colors)

    def test_resize_keeps_canvas_and_centers_picture_with_black_bars(self):
        canvas = self.display.canvas
        color = (17, 41, 69)
        canvas.fill(color)
        self.assertTrue(self.display.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=1920, h=1080)))
        self.display.present()
        self.assertIs(self.display.canvas, canvas)
        self.assertEqual(canvas.get_size(), (800, 600))
        self.assertEqual(scaled_viewport((800, 600), (1920, 1080)), pygame.Rect(240, 0, 1440, 1080))
        for point in ((0, 540), (239, 0), (1680, 1079)):
            self.assertEqual(tuple(self.display.window.get_at(point))[:3], (0, 0, 0))
        for point in ((240, 0), (1679, 1079)):
            self.assertEqual(tuple(self.display.window.get_at(point))[:3], color)

    def test_portrait_viewport_has_top_and_bottom_bars(self):
        self.assertEqual(scaled_viewport((800, 600), (900, 1200)), pygame.Rect(0, 262, 900, 675))
        tiny = scaled_viewport((800, 600), (1, 1))
        self.assertEqual(tiny.size, (1, 1))

    def test_f11_restores_window_size_without_changing_canvas(self):
        canvas = self.display.canvas
        canvas.set_at((400, 300), (255, 0, 0))
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11)
        self.assertTrue(self.display.handle_event(event))
        self.assertTrue(self.display.fullscreen)
        self.display.present()
        self.display.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11, repeat=True))
        self.assertTrue(self.display.fullscreen)
        self.display.handle_event(event)
        self.assertFalse(self.display.fullscreen)
        self.assertEqual(self.display.window.get_size(), (1600, 1200))
        self.assertIs(self.display.canvas, canvas)
        self.assertEqual(tuple(canvas.get_at((400, 300)))[:3], (255, 0, 0))

    def test_resizing_does_not_reset_or_change_game_coordinates(self):
        game = Game(self.display.canvas)
        game.reset(start_phase=4)
        game.ready_timer = 0
        game.add_score(200)
        game.extra_stage.boss.hp = 123
        keys = defaultdict(bool, {pygame.K_w: True, pygame.K_d: True})
        game.update(0.1, keys)
        self.display.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=1200, h=900))
        game.draw()
        self.display.present()
        game.update(0.1, keys)
        self.assertIs(game.screen, self.display.canvas)
        self.assertAlmostEqual(game.player_x, 400 + 36 / math.sqrt(2))
        self.assertAlmostEqual(game.player_y, 540 - 36 / math.sqrt(2))
        self.assertEqual(game.score, 200)
        self.assertEqual(game.extra_stage.boss.hp, 123)
        self.assertEqual(game.state, "playing")


if __name__ == "__main__":
    unittest.main()
