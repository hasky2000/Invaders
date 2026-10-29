"""画面遷移、日本語表示、練習課題と長押しスキップの回帰テスト。"""

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
from main import Bullet, Game, PLAYER_LIVES, WAVE_CLEAR_TIME, WAVE_READY_TIME
from tutorial import INSTRUCTIONS, TutorialProgress, TutorialStep


class TutorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()
        cls.screen = pygame.display.set_mode((800, 600))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.game = Game(self.screen)
        directory = tempfile.TemporaryDirectory(prefix="invaders-tutorial-test-")
        self.addCleanup(directory.cleanup)
        self.game.results_path = Path(directory.name) / "results.json"
        self.keys = defaultdict(bool)

    def press(self, key):
        self.keys[key] = True
        return self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))

    def release(self, key):
        self.keys[key] = False
        self.game.handle_event(pygame.event.Event(pygame.KEYUP, key=key))

    def tick(self, duration, pad=None):
        # 実際のメインループと同じ短いフレームで、弾や演出も更新する。
        frames = round(duration * 120)
        for _ in range(frames):
            self.game.update(1 / 120, self.keys, pad)

    def practice(self, step):
        self.game.start_tutorial()
        self.game.tutorial.step = step
        self.game.prepare_tutorial_step()

    def shoot_enemy(self, alien):
        bullet = Bullet(*alien.rect.center, -510, True)
        self.game.bullets.append(bullet)
        self.game.resolve_player_bullet(bullet)

    def assert_fresh_phase_one(self):
        self.assertIsNone(self.game.tutorial)
        self.assertEqual(self.game.state, "playing")
        self.assertEqual(self.game.wave, 1)
        self.assertEqual(self.game.score, 0)
        self.assertEqual(self.game.lives, PLAYER_LIVES)
        self.assertEqual(self.game.bombs_left, 1)
        self.assertEqual(self.game.player_x, 400)
        self.assertEqual(len(self.game.aliens), 60)
        self.assertEqual(len(self.game.shields), 4)
        self.assertEqual(self.game.ready_timer, WAVE_READY_TIME)
        self.assertFalse(self.game.bullets)
        self.assertFalse(self.game.falling_aliens)
        self.assertFalse(self.game.explosions)
        self.assertFalse(self.game.popups)
        self.assertIsNone(self.game.extra_stage)

    def test_title_draws_only_the_two_labels_over_background(self):
        self.game.gamepad_name = "PS3 Controller"
        with patch.object(self.game, "draw_text", wraps=self.game.draw_text) as draw:
            self.game.draw()
        self.assertEqual([call.args[0] for call in draw.call_args_list], ["SPACE INVADERS", "PRESS ANY KEY"])
        # HUDと敵の位置には、背景以外を描かない。
        for rect in (pygame.Rect(0, 0, 800, 200), pygame.Rect(0, 400, 800, 200)):
            actual = pygame.image.tobytes(self.screen.subsurface(rect), "RGB")
            expected = pygame.image.tobytes(self.game.background.subsurface(rect), "RGB")
            self.assertEqual(actual, expected)

    def test_any_ordinary_key_starts_phase_zero(self):
        for key in (pygame.K_q, pygame.K_1, pygame.K_SPACE, pygame.K_LEFT, pygame.K_RETURN):
            self.game.state = "title"
            self.press(key)
            self.assertEqual(self.game.tutorial.step, TutorialStep.MOVE)
            self.assertFalse(self.game.aliens)
            self.assertEqual(self.game.wave, 1)
            self.release(key)

    def test_title_input_must_be_released_before_moving_or_skipping(self):
        self.press(pygame.K_RIGHT)
        self.tick(2.2)
        self.assertEqual(self.game.player_x, 400)
        self.assertEqual(self.game.tutorial.skip_progress, 0)
        self.release(pygame.K_RIGHT)
        self.press(pygame.K_RIGHT)
        self.tick(0.1)
        self.assertGreater(self.game.player_x, 400)
        self.assertEqual(self.game.tutorial.skip_progress, 0)

    def test_move_then_fire_requires_real_actions_in_order(self):
        self.game.start_tutorial()
        self.press(pygame.K_SPACE)
        self.tick(0.1)
        self.release(pygame.K_SPACE)
        self.assertFalse(self.game.bullets)
        self.assertEqual(self.game.tutorial.step, TutorialStep.MOVE)
        self.press(pygame.K_RIGHT)
        self.tick(0.1)
        self.release(pygame.K_RIGHT)
        self.assertEqual(self.game.tutorial.step, TutorialStep.MOVE)
        self.press(pygame.K_a)
        self.tick(0.1)
        self.release(pygame.K_a)
        self.assertEqual(self.game.tutorial.step, TutorialStep.FIRE)
        self.assertFalse(self.game.aliens)
        self.tick(0.1)
        self.assertEqual(self.game.tutorial.step, TutorialStep.FIRE)
        self.press(pygame.K_SPACE)
        self.tick(0.05)
        self.assertEqual(self.game.tutorial.step, TutorialStep.ONE_ENEMY)
        self.assertEqual(len(self.game.aliens), 1)

    def test_boundary_input_does_not_count_as_movement(self):
        self.game.start_tutorial()
        self.game.player_x = 28 + self.game.player_image.get_width() / 2
        self.press(pygame.K_LEFT)
        self.tick(0.2)
        self.assertEqual(self.game.tutorial.left_distance, 0)

    def test_fire_step_does_not_pass_when_bullet_limit_prevents_shooting(self):
        self.practice(TutorialStep.FIRE)
        self.game.bullets = [Bullet(300, 300, -510, True), Bullet(310, 300, -510, True)]
        self.press(pygame.K_SPACE)
        self.tick(0.05)
        self.assertEqual(self.game.tutorial.step, TutorialStep.FIRE)
        self.game.bullets.clear()
        self.tick(0.05)
        self.assertEqual(self.game.tutorial.step, TutorialStep.ONE_ENEMY)

    def test_one_enemy_waits_for_effects_then_spawns_four(self):
        self.practice(TutorialStep.ONE_ENEMY)
        self.game.high_score = 123
        self.shoot_enemy(self.game.aliens[0])
        self.tick(0.1)
        self.assertEqual(self.game.tutorial.step, TutorialStep.ONE_ENEMY)
        self.assertEqual(self.game.wave_timer, 0)
        self.tick(1.1)
        self.assertEqual(self.game.tutorial.step, TutorialStep.BOMB)
        self.assertEqual(len(self.game.aliens), 4)
        self.assertEqual(len({enemy.rect.x for enemy in self.game.aliens}), 2)
        self.assertEqual(len({enemy.rect.y for enemy in self.game.aliens}), 2)
        self.assertEqual(self.game.score, 0)
        self.assertEqual(self.game.high_score, 123)

    def test_bomb_exercise_waits_for_effects_then_moves_to_damage(self):
        self.practice(TutorialStep.BOMB)
        self.press(pygame.K_b)
        self.release(pygame.K_b)
        self.assertTrue(self.game.tutorial.bomb_launched)
        self.assertEqual(self.game.bombs_left, 0)
        self.tick(0.2)
        self.assertEqual(self.game.tutorial.step, TutorialStep.BOMB)
        for _ in range(360):
            self.game.update(1 / 120, self.keys)
            if self.game.tutorial.step != TutorialStep.BOMB:
                break
        self.assertEqual(self.game.tutorial.step, TutorialStep.DAMAGE)
        self.assertFalse(self.game.tutorial.complete)
        self.assertEqual(self.game.wave_timer, 0)
        self.assertEqual(self.game.score, 0)

    def test_phase_explanation_waits_for_confirmation_then_starts_fresh(self):
        self.practice(TutorialStep.PHASES)
        self.press(pygame.K_RETURN)
        self.release(pygame.K_RETURN)
        self.assertFalse(self.game.tutorial.complete)
        self.tick(1.1)
        self.assertEqual(self.game.tutorial.step, TutorialStep.PHASES)
        self.press(pygame.K_RETURN)
        self.release(pygame.K_RETURN)
        self.assertTrue(self.game.tutorial.complete)
        self.assertEqual(self.game.wave_timer, WAVE_CLEAR_TIME)
        self.tick(0.5)
        self.assertIsNotNone(self.game.tutorial)
        # 最終フレームでリセットされるまで進め、初期待機を減らさない。
        for _ in range(120):
            self.game.update(1 / 120, self.keys)
            if self.game.tutorial is None:
                break
        self.assert_fresh_phase_one()

    def test_practice_uses_phase_one_motion_fire_and_damage(self):
        self.practice(TutorialStep.ONE_ENEMY)
        initial = [enemy.rect.copy() for enemy in self.game.aliens]
        self.game.enemy_shot_timer = 0
        self.tick(0.6)
        self.assertTrue(any(enemy.rect != rect for enemy, rect in zip(self.game.aliens, initial)))
        self.assertTrue(any(not bullet.friendly for bullet in self.game.bullets))
        self.game.bullets = [Bullet(*self.game.player_hitbox.center, 0, False)]
        self.tick(0.01)
        self.assertEqual(self.game.lives, 4)
        self.assertFalse(self.game.shields)
        self.press(pygame.K_b)
        self.assertIsNone(self.game.bomb)
        self.assertIsNone(self.game.ufo_x)

    def test_death_and_invasion_restart_current_practice(self):
        for step in (TutorialStep.ONE_ENEMY, TutorialStep.BOMB):
            for failure in ("death", "invasion"):
                self.practice(step)
                self.game.lives = 1
                if failure == "death":
                    self.game.bullets = [Bullet(*self.game.player_hitbox.center, 0, False)]
                else:
                    self.game.aliens[0].rect.bottom = self.game.player_rect.top
                self.tick(0.01)
                self.assertEqual(self.game.tutorial.step, step)
                self.assertEqual(self.game.state, "playing")
                self.assertEqual(self.game.lives, PLAYER_LIVES)
                self.assertEqual(len(self.game.aliens), self.game.tutorial.enemy_count)
                self.assertFalse(self.game.bullets)

    def test_same_arbitrary_key_skips_at_two_seconds_and_resets_gameplay(self):
        self.practice(TutorialStep.BOMB)
        self.game.lives = 2
        self.game.player_x = 200
        self.game.high_score = 500
        self.press(pygame.K_q)
        self.tick(1.9)
        self.assertIsNotNone(self.game.tutorial)
        self.assertAlmostEqual(self.game.tutorial.skip_progress, 0.95)
        for _ in range(20):
            self.game.update(1 / 120, self.keys)
            if self.game.tutorial is None:
                break
        self.assert_fresh_phase_one()
        self.assertEqual(self.game.high_score, 500)

    def test_keys_are_not_added_together_and_release_resets_timer(self):
        self.game.start_tutorial()
        self.press(pygame.K_q)
        self.tick(1.2)
        self.release(pygame.K_q)
        self.press(pygame.K_e)
        self.tick(1.2)
        self.assertAlmostEqual(self.game.tutorial.skip_progress, 0.6)
        self.release(pygame.K_e)
        self.press(pygame.K_e)
        self.tick(0.2)
        self.assertAlmostEqual(self.game.tutorial.skip_progress, 0.1)

    def test_simultaneous_keys_have_independent_timers(self):
        tutorial = TutorialProgress()
        tutorial.update_holds(1.0, {1})
        tutorial.update_holds(0.5, {1, 2})
        tutorial.update_holds(0.4, {2})
        self.assertAlmostEqual(tutorial.skip_progress, 0.45)
        self.assertFalse(tutorial.update_holds(1.0, {2}))
        self.assertTrue(tutorial.update_holds(0.1, {2}))

    def test_held_time_continues_across_steps(self):
        self.game.start_tutorial()
        self.press(pygame.K_q)
        self.tick(1.0)
        self.game.advance_tutorial()
        self.tick(0.5)
        self.assertAlmostEqual(self.game.tutorial.skip_progress, 0.75)

    def test_gameplay_and_menu_keys_do_not_skip_tutorial(self):
        for key in (
            pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN,
            pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d,
            pygame.K_SPACE, pygame.K_b, pygame.K_LSHIFT, pygame.K_RSHIFT,
            pygame.K_RETURN, pygame.K_F2, pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
        ):
            with self.subTest(key=pygame.key.name(key)):
                self.game.start_tutorial()
                self.press(key)
                self.tick(2.1)
                self.assertIsNotNone(self.game.tutorial)
                self.assertEqual(self.game.tutorial.skip_progress, 0)
                self.release(key)

    def test_unbound_key_can_skip_while_an_operation_key_is_held(self):
        self.game.start_tutorial()
        self.press(pygame.K_SPACE)
        self.tick(1.5)
        self.press(pygame.K_TAB)
        self.tick(1.5)
        self.assertIsNotNone(self.game.tutorial)
        self.assertAlmostEqual(self.game.tutorial.skip_progress, 0.75)
        self.tick(0.6)
        self.assertIsNone(self.game.tutorial)

    def test_held_fire_keeps_shooting_without_skipping(self):
        self.practice(TutorialStep.ONE_ENEMY)
        self.game.player_x = 100  # 撃墜による課題完了を避けて射撃の継続を確認する。
        self.press(pygame.K_SPACE)
        with patch.object(self.game.sounds, "play") as play:
            self.tick(2.5)
        self.assertIsNotNone(self.game.tutorial)
        self.assertEqual(self.game.tutorial.skip_progress, 0)
        self.assertGreater(sum(call.args == ("shoot",) for call in play.call_args_list), 2)

    def test_focus_loss_clears_held_input_without_pausing(self):
        self.game.start_tutorial()
        self.press(pygame.K_q)
        self.tick(1.0)
        self.game.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        self.tick(0.1)
        self.assertEqual(self.game.state, "playing")
        self.assertEqual(self.game.tutorial.skip_progress, 0)
        self.assertEqual(self.game.tutorial.step, TutorialStep.MOVE)

    def test_reserved_shortcuts_keep_their_functions(self):
        self.assertFalse(self.press(pygame.K_ESCAPE))
        self.game.start_tutorial()
        self.press(pygame.K_F11)
        self.tick(2.2)
        self.assertIsNotNone(self.game.tutorial)

    def test_bomb_miss_refills_and_other_lessons_cannot_use_bombs(self):
        self.practice(TutorialStep.BOMB)
        self.game.player_x = 80
        self.press(pygame.K_b)
        self.release(pygame.K_b)
        self.game.bomb.y = 90
        self.tick(0.6)
        self.assertEqual(self.game.tutorial.step, TutorialStep.BOMB)
        self.assertEqual(self.game.bombs_left, 1)
        self.assertEqual(len(self.game.aliens), 4)
        for step in (TutorialStep.MOVE, TutorialStep.FIRE, TutorialStep.ONE_ENEMY, TutorialStep.DAMAGE, TutorialStep.PHASES):
            self.practice(step)
            self.game.bombs_left = 1
            self.press(pygame.K_b)
            self.release(pygame.K_b)
            self.assertIsNone(self.game.bomb)

    def test_pad_bomb_requires_release_when_entering_bomb_lesson(self):
        self.practice(TutorialStep.BOMB)
        held = GamepadInput(bomb_held=True, actions=("bomb",))
        self.game.handle_gamepad(held)
        self.assertIsNone(self.game.bomb)
        self.game.handle_gamepad(GamepadInput())
        self.game.handle_gamepad(held)
        self.assertIsNotNone(self.game.bomb)
        self.assertTrue(self.game.tutorial.bomb_launched)
        self.assertEqual(self.game.bombs_left, 0)

    def test_damage_lesson_demonstrates_a_lost_heart_and_invincibility(self):
        self.practice(TutorialStep.DAMAGE)
        self.assertEqual(self.game.lives, 5)
        self.tick(3.0)
        self.assertTrue(self.game.tutorial.damage_taken)
        self.assertEqual(self.game.lives, 4)
        self.assertGreater(self.game.invincible, 0)
        self.assertEqual(self.game.tutorial.step, TutorialStep.DAMAGE)
        self.game.bullets.append(Bullet(*self.game.player_hitbox.center, 0, False))
        self.tick(0.1)
        self.assertEqual(self.game.lives, 4)
        self.tick(1.8)
        self.assertEqual(self.game.tutorial.step, TutorialStep.PHASES)
        self.assertFalse(self.game.tutorial.complete)
        self.assertEqual(self.game.wave_timer, 0)

    def test_phase_lesson_can_be_confirmed_with_pad_after_reading(self):
        self.practice(TutorialStep.PHASES)
        self.game.handle_gamepad(GamepadInput(fire=True, actions=("confirm",)))
        self.assertFalse(self.game.tutorial.complete)
        self.tick(1.1, GamepadInput(fire=True))
        self.assertFalse(self.game.tutorial.complete)
        self.game.handle_gamepad(GamepadInput(fire=True, actions=("confirm",)))
        self.assertTrue(self.game.tutorial.complete)

    def test_failed_practice_does_not_record_a_player_result(self):
        self.practice(TutorialStep.ONE_ENEMY)
        previous_results = list(self.game.results)
        self.game.lives = 1
        self.game.bullets = [Bullet(*self.game.player_hitbox.center, 0, False)]
        self.tick(0.01)
        self.assertEqual(self.game.state, "playing")
        self.assertEqual(self.game.tutorial.step, TutorialStep.ONE_ENEMY)
        self.assertEqual(self.game.results, previous_results)
        self.assertFalse(self.game.results_path.exists())

    def test_gamepad_start_input_is_blocked_until_release(self):
        held = GamepadInput(movement=(1, 0), fire=True, actions=("confirm", "start"))
        self.game.handle_gamepad(held)
        self.tick(2.2, held)
        self.assertEqual(self.game.state, "playing")
        self.assertEqual(self.game.player_x, 400)
        self.assertEqual(self.game.tutorial.skip_progress, 0)
        self.tick(0.1, GamepadInput())
        self.tick(0.1, GamepadInput(movement=(-1, 0)))
        self.tick(0.1, GamepadInput(movement=(1, 0)))
        self.assertEqual(self.game.tutorial.step, TutorialStep.FIRE)
        self.tick(0.05, GamepadInput(fire=True))
        self.assertEqual(self.game.tutorial.step, TutorialStep.ONE_ENEMY)
        self.tick(2.1, GamepadInput(fire=True))
        self.assertIsNotNone(self.game.tutorial)
        self.assertEqual(self.game.tutorial.skip_progress, 0)

    def test_keyboard_start_also_blocks_the_initial_gamepad_input(self):
        self.press(pygame.K_RETURN)
        self.tick(2.2, GamepadInput(movement=(1, 0), fire=True))
        self.assertEqual(self.game.player_x, 400)
        self.assertEqual(self.game.tutorial.skip_progress, 0)
        self.tick(0.1, GamepadInput())
        self.tick(0.1, GamepadInput(movement=(1, 0)))
        self.assertGreater(self.game.player_x, 400)

    def test_key_repeat_does_not_restart_tutorial_or_reset_hold_time(self):
        self.game.start_tutorial()
        self.press(pygame.K_q)
        self.tick(1.0)
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q, repeat=True))
        self.tick(0.5)
        self.assertAlmostEqual(self.game.tutorial.skip_progress, 0.75)
        self.release(pygame.K_q)
        self.press(pygame.K_q)
        self.assertEqual(self.game.tutorial.skip_progress, 0)

    def test_missing_bundled_japanese_font_reports_its_path(self):
        with patch("main.Path.is_file", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "fonts/DotGothic16-Regular.ttf"):
                Game(self.screen)

    def test_debug_back_and_end_screen_retries(self):
        self.press(pygame.K_F2)
        self.assertEqual(self.game.state, "debug")
        self.press(pygame.K_4)
        self.assertEqual(self.game.start_phase, 4)
        self.press(pygame.K_F2)
        self.assertEqual(self.game.state, "title")
        self.press(pygame.K_RETURN)
        self.assertIsNotNone(self.game.tutorial)
        for state in ("game_over", "victory"):
            self.game.reset(start_phase=4)
            self.game.state = state
            self.press(pygame.K_RETURN)
            self.assert_fresh_phase_one()

    def test_japanese_labels_fit_and_render_without_missing_glyphs(self):
        self.game.start_tutorial()
        self.game.gamepad_name = "PS3 Controller"
        self.game.gamepad_hint = "X:FIRE O:BOMB"
        for step in TutorialStep:
            self.game.tutorial.step = step
            self.game.prepare_tutorial_step()
            self.game.draw()
        for (text, _), image in self.game.japanese_text_cache.items():
            self.assertLessEqual(image.get_width(), 744, text)
            self.assertTrue(all(metric is not None for metric in self.game.japanese_font.metrics(text)), text)
        self.assertTrue(all(text in {key[0] for key in self.game.japanese_text_cache} for text in INSTRUCTIONS))


if __name__ == "__main__":
    unittest.main()
