"""外部設定と、EXTRAを無効にしたときの進行・操作・表示を検証する。"""

import os
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from controls import GamepadInput
from main import Game, WAVE_CLEAR_TIME
from settings import Settings, load_settings
from tutorial import TutorialStep


class SettingsTests(unittest.TestCase):
    def test_missing_file_or_option_keeps_extra_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.ini"
            self.assertTrue(load_settings(path).extra_enabled)
            for content in ("", "[game]\n"):
                path.write_text(content, encoding="utf-8")
                self.assertTrue(load_settings(path).extra_enabled)

    def test_reads_enabled_and_disabled_from_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.ini"
            for value, expected in (("true", True), ("false", False)):
                with self.subTest(value=value):
                    path.write_text(f"[game]\nextra_enabled = {value}\n", encoding="utf-8")
                    self.assertEqual(load_settings(path).extra_enabled, expected)

    def test_invalid_boolean_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.ini"
            path.write_text("[game]\nextra_enabled = typo\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_settings(path)


class ExtraSettingGameplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()
        cls.screen = pygame.display.set_mode((800, 600))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.game = Game(self.screen, settings=Settings(extra_enabled=False))
        directory = tempfile.TemporaryDirectory(prefix="invaders-settings-test-")
        self.addCleanup(directory.cleanup)
        self.game.results_path = Path(directory.name) / "results.json"
        self.game.results = []

    def test_game_loads_external_settings_at_startup(self):
        with patch("main.load_settings", return_value=Settings(extra_enabled=False)) as load:
            game = Game(self.screen)
        load.assert_called_once_with()
        self.assertFalse(game.settings.extra_enabled)

    def test_phase_three_clear_respects_setting_for_all_life_counts(self):
        for enabled in (False, True):
            self.game.settings = Settings(extra_enabled=enabled)
            for lives in range(1, 6):
                with self.subTest(enabled=enabled, lives=lives):
                    self.game.reset(start_phase=3)
                    self.game.lives = lives
                    self.game.ready_timer = 0
                    self.game.aliens.clear()
                    self.game.update(0, defaultdict(bool))
                    self.game.update(WAVE_CLEAR_TIME + 0.01, defaultdict(bool))
                    enters_extra = enabled and lives >= 3
                    self.assertEqual(self.game.extra_stage is not None, enters_extra)
                    self.assertEqual(self.game.state, "playing" if enters_extra else "results")
                    if not enters_extra:
                        self.assertEqual(self.game.current_result["outcome"], "clear")

    def test_keyboard_cannot_select_extra_and_pad_wraps_at_three(self):
        self.game.state = "debug"
        for phase, key in ((1, pygame.K_1), (2, pygame.K_2), (3, pygame.K_3)):
            self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
            self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4))
            self.assertEqual(self.game.start_phase, phase)
        self.game.handle_gamepad(GamepadInput(actions=("next_phase",)))
        self.assertEqual(self.game.start_phase, 1)
        self.game.handle_gamepad(GamepadInput(actions=("previous_phase",)))
        self.assertEqual(self.game.start_phase, 3)
        self.game.handle_gamepad(GamepadInput(actions=("confirm",)))
        self.assertEqual(self.game.wave, 3)
        self.assertIsNone(self.game.extra_stage)

    def test_direct_start_cannot_bypass_disabled_setting(self):
        self.game.reset(start_phase=4)
        self.assertEqual(self.game.start_phase, 3)
        self.assertEqual(self.game.wave, 3)
        self.assertIsNone(self.game.extra_stage)
        self.game.prepare_wave(extra=True)
        self.assertIsNone(self.game.extra_stage)

    def test_debug_and_tutorial_do_not_mention_extra_when_disabled(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.game.settings = Settings(extra_enabled=enabled)
                self.game.state = "debug"
                with patch.object(self.game, "draw_text") as draw:
                    self.game.draw()
                labels = [call.args[0] for call in draw.call_args_list]
                self.assertEqual(any("EXTRA" in text for text in labels), enabled)
                self.game.start_tutorial()
                self.game.tutorial.step = TutorialStep.PHASES
                self.game.prepare_tutorial_step()
                with patch.object(self.game, "draw_japanese") as draw:
                    self.game.draw()
                labels = [call.args[0] for call in draw.call_args_list]
                self.assertEqual(any("EXTRA" in text for text in labels), enabled)
                if not enabled:
                    self.assertIn("PHASE 3をクリアすると本編クリアです", labels)


if __name__ == "__main__":
    unittest.main()
