"""ゲームパッドの中央補正、押下操作、再接続とゲーム側の操作を検証する。"""

import math
import os
import unittest
from collections import defaultdict
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from controls import Gamepad, GamepadInput, stick_movement
from main import Game


class FakeController:
    name = "PS3 Controller"

    def __init__(self):
        self.axes = defaultdict(int)
        self.buttons = set()
        self.connected = True
        self.closed = False

    def attached(self):
        return self.connected

    def get_axis(self, axis):
        return self.axes[axis]

    def get_button(self, button):
        return button in self.buttons

    def quit(self):
        self.closed = True


class GamepadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.patch_api = patch("controls.sdl_controller", autospec=True)
        self.api = self.patch_api.start()
        self.api.get_count.return_value = 1
        self.api.is_controller.return_value = True
        self.device = FakeController()
        self.api.Controller.return_value = self.device
        self.pad = Gamepad()

    def tearDown(self):
        self.pad.close()
        self.patch_api.stop()

    def test_connected_ps3_has_correct_control_hint(self):
        self.assertEqual(self.pad.name, "PS3 Controller")
        self.assertIn("X:FIRE O:BOMB", self.pad.hint)

    def test_neutral_drift_does_not_move_and_analogue_tilt_is_proportional(self):
        self.device.axes[pygame.CONTROLLER_AXIS_LEFTX] = 899
        self.device.axes[pygame.CONTROLLER_AXIS_LEFTY] = -129
        self.assertEqual(self.pad.poll().movement, (0, 0))
        self.device.axes[pygame.CONTROLLER_AXIS_LEFTX] = 16384
        self.device.axes[pygame.CONTROLLER_AXIS_LEFTY] = 0
        x, y = self.pad.poll().movement
        self.assertAlmostEqual(x, 0.39, places=2)
        self.assertEqual(y, 0)
        self.device.axes[pygame.CONTROLLER_AXIS_LEFTX] = 32767
        self.assertEqual(self.pad.poll().movement, (1, 0))

    def test_diagonal_stick_and_dpad_cannot_exceed_full_speed(self):
        self.device.axes[pygame.CONTROLLER_AXIS_LEFTX] = 32767
        self.device.axes[pygame.CONTROLLER_AXIS_LEFTY] = -32768
        state = self.pad.poll()
        self.assertAlmostEqual(math.hypot(*state.movement), 1)
        self.device.buttons = {pygame.CONTROLLER_BUTTON_DPAD_LEFT, pygame.CONTROLLER_BUTTON_DPAD_DOWN}
        state = self.pad.poll()
        self.assertAlmostEqual(math.hypot(*state.movement), 1)
        self.assertLess(state.movement[0], 0)
        self.assertGreater(state.movement[1], 0)

    def test_fire_is_held_but_confirm_and_bomb_are_pressed_once(self):
        self.device.buttons = {pygame.CONTROLLER_BUTTON_A}
        first = self.pad.poll()
        self.assertTrue(first.fire)
        self.assertIn("confirm", first.actions)
        held = self.pad.poll()
        self.assertTrue(held.fire)
        self.assertNotIn("confirm", held.actions)
        self.device.buttons.add(pygame.CONTROLLER_BUTTON_B)
        self.assertIn("bomb", self.pad.poll().actions)
        self.assertNotIn("bomb", self.pad.poll().actions)
        self.device.buttons.remove(pygame.CONTROLLER_BUTTON_B)
        self.pad.poll()
        self.device.buttons.add(pygame.CONTROLLER_BUTTON_B)
        self.assertIn("bomb", self.pad.poll().actions)

    def test_reconnect_does_not_treat_held_bomb_as_a_new_press(self):
        self.pad.disconnect()
        self.device.buttons = {pygame.CONTROLLER_BUTTON_B}
        self.pad.connect()
        initial = self.pad.poll()
        self.assertNotIn("bomb", initial.actions)
        self.assertTrue(initial.bomb_held)
        self.assertNotIn("bomb", self.pad.poll().actions)
        self.device.buttons.clear()
        self.pad.poll()
        self.device.buttons.add(pygame.CONTROLLER_BUTTON_B)
        self.assertIn("bomb", self.pad.poll().actions)

    def test_start_and_select_do_not_repeat_while_held(self):
        self.device.buttons = {pygame.CONTROLLER_BUTTON_START, pygame.CONTROLLER_BUTTON_BACK}
        self.assertEqual(self.pad.poll().actions, ("start", "mute"))
        self.assertEqual(self.pad.poll().actions, ())

    def test_either_shoulder_button_enables_precision(self):
        for shoulder in (pygame.CONTROLLER_BUTTON_LEFTSHOULDER, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER):
            self.device.buttons = {shoulder}
            self.assertTrue(self.pad.poll().precise)
        self.device.buttons.clear()
        self.assertFalse(self.pad.poll().precise)

    def test_menu_selection_uses_stick_or_dpad_without_repeating(self):
        self.device.axes[pygame.CONTROLLER_AXIS_LEFTX] = 32767
        self.assertIn("next_phase", self.pad.poll().actions)
        self.assertNotIn("next_phase", self.pad.poll().actions)
        self.device.axes[pygame.CONTROLLER_AXIS_LEFTX] = 0
        self.pad.poll()
        self.device.buttons = {pygame.CONTROLLER_BUTTON_DPAD_LEFT}
        self.assertIn("previous_phase", self.pad.poll().actions)

    def test_disconnect_stops_held_input_and_reconnects(self):
        self.device.buttons = {pygame.CONTROLLER_BUTTON_A}
        self.pad.poll()
        self.device.connected = False
        self.api.get_count.return_value = 0
        state = self.pad.poll()
        self.assertEqual(state.actions, ("disconnected",))
        self.assertFalse(state.fire)
        self.assertEqual(state.movement, (0, 0))
        self.assertTrue(self.device.closed)
        self.assertEqual(self.pad.poll().actions, ())
        self.api.get_count.return_value = 1
        self.api.Controller.return_value = FakeController()
        self.assertEqual(self.pad.poll(), GamepadInput())
        self.assertEqual(self.pad.name, "PS3 Controller")

    def test_device_read_error_is_treated_as_disconnect(self):
        with patch.object(self.device, "get_axis", side_effect=pygame.error("unplugged")):
            self.assertEqual(self.pad.poll().actions, ("disconnected",))
        self.assertIsNone(self.pad.device)

    def test_absent_or_unmapped_controller_is_optional(self):
        self.pad.disconnect()
        self.api.is_controller.return_value = False
        self.assertEqual(self.pad.poll(), GamepadInput())
        self.assertEqual(self.pad.name, "")
        self.api.get_count.return_value = 0
        self.assertEqual(self.pad.poll(), GamepadInput())

    def test_deadzone_is_continuous_at_center_and_clamps_large_values(self):
        self.assertEqual(stick_movement(0.18, 0), pygame.Vector2())
        self.assertLess(stick_movement(0.181, 0).length(), 0.002)
        self.assertAlmostEqual(stick_movement(1.1, 1.1).length(), 1)


class GamepadGameplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()
        cls.screen = pygame.display.set_mode((800, 600))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.game = Game(self.screen)
        self.keys = defaultdict(bool)

    def test_start_confirm_phase_selection_pause_and_resume(self):
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2))
        self.game.handle_gamepad(GamepadInput(actions=("previous_phase",)))
        self.assertEqual(self.game.start_phase, 4)
        self.assertEqual(self.game.state, "debug")
        self.game.handle_gamepad(GamepadInput(actions=("confirm",)))
        self.assertEqual(self.game.state, "playing")
        self.assertIsNotNone(self.game.extra_stage)
        self.game.handle_gamepad(GamepadInput(actions=("start",)))
        self.assertEqual(self.game.state, "paused")
        self.game.handle_gamepad(GamepadInput(actions=("start",)))
        self.assertEqual(self.game.state, "playing")
        self.game.handle_gamepad(GamepadInput(actions=("next_phase",)))
        self.assertEqual(self.game.start_phase, 4)  # プレイ中はメニュー選択しない。
        self.game.state = "game_over"
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2))
        self.game.handle_gamepad(GamepadInput(actions=("next_phase",)))
        self.assertEqual(self.game.start_phase, 1)
        self.game.handle_gamepad(GamepadInput(actions=("start",)))
        self.assertEqual(self.game.state, "playing")

    def test_gamepad_moves_fires_and_launches_bomb_in_normal_phase(self):
        self.game.reset()
        self.game.ready_timer = 0
        initial_y = self.game.player_y
        self.game.update(0.1, self.keys, GamepadInput(movement=(0.5, -0.5), fire=True))
        self.assertAlmostEqual(self.game.player_x, 413)
        self.assertEqual(self.game.player_y, initial_y)
        self.assertEqual(sum(bullet.friendly for bullet in self.game.bullets), 1)
        self.game.handle_gamepad(GamepadInput(actions=("bomb",)))
        self.assertIsNotNone(self.game.bomb)
        self.assertEqual(self.game.bombs_left, 0)

    def test_extra_supports_proportional_two_axis_movement_and_precision(self):
        for precise, speed in ((False, 180), (True, 90)):
            self.game.reset(start_phase=4)
            self.game.ready_timer = 0
            self.game.player_y = 400
            self.game.update(0.1, self.keys, GamepadInput(movement=(0.3, -0.4), precise=precise))
            self.assertAlmostEqual(self.game.player_x, 400 + 0.3 * speed * 0.1)
            self.assertAlmostEqual(self.game.player_y, 400 - 0.4 * speed * 0.1)
            self.assertEqual(sum(bullet.friendly for bullet in self.game.bullets), 1)

    def test_keyboard_and_gamepad_combination_cannot_double_speed(self):
        self.game.reset()
        self.game.ready_timer = 0
        self.keys[pygame.K_RIGHT] = True
        self.game.update(0.1, self.keys, GamepadInput(movement=(1, 0)))
        self.assertAlmostEqual(self.game.player_x, 426)

    def test_disconnect_pauses_once_and_keyboard_can_resume(self):
        self.game.reset()
        state = GamepadInput(actions=("disconnected",))
        self.game.handle_gamepad(state)
        self.assertEqual(self.game.state, "paused")
        self.game.handle_gamepad(state)
        self.assertEqual(self.game.state, "paused")
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p))
        self.assertEqual(self.game.state, "playing")
        self.game.handle_gamepad(GamepadInput(actions=("mute",)))
        self.assertTrue(self.game.sounds.muted)

    def test_resume_does_not_launch_bomb_in_the_same_input(self):
        for actions in (("start", "bomb"), ("bomb", "start")):
            with self.subTest(actions=actions):
                self.game.reset()
                self.game.ready_timer = 0
                self.game.toggle_pause()
                self.game.handle_gamepad(GamepadInput(actions=actions))
                self.assertEqual(self.game.state, "playing")
                self.assertIsNone(self.game.bomb)
                self.assertEqual(self.game.bombs_left, 1)

    def test_keyboard_resume_after_reconnection_does_not_launch_held_bomb(self):
        device = FakeController()
        device.buttons = {pygame.CONTROLLER_BUTTON_B}
        with patch("controls.sdl_controller", autospec=True) as api:
            api.get_count.return_value = 1
            api.is_controller.return_value = True
            api.Controller.return_value = device
            pad = Gamepad()
            try:
                self.game.reset()
                self.game.ready_timer = 0
                self.game.toggle_pause()
                self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p))
                self.game.handle_gamepad(pad.poll())
                self.assertIsNone(self.game.bomb)
                self.assertEqual(self.game.bombs_left, 1)
            finally:
                pad.close()

    def test_held_bomb_requires_release_after_ready_or_pause(self):
        held = GamepadInput(bomb_held=True, actions=("bomb",))
        for transition in ("ready", "keyboard_resume", "pad_resume"):
            with self.subTest(transition=transition):
                self.game.reset()
                self.game.ready_timer = 0
                self.game.handle_gamepad(GamepadInput())
                if transition == "ready":
                    self.game.ready_timer = 0.1
                    self.game.handle_gamepad(held)
                    self.game.ready_timer = 0
                else:
                    self.game.toggle_pause()
                    self.game.handle_gamepad(held)
                    if transition == "keyboard_resume":
                        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p))
                    else:
                        self.game.handle_gamepad(GamepadInput(bomb_held=True, actions=("start", "bomb")))
                self.game.handle_gamepad(held)
                self.assertIsNone(self.game.bomb)
                self.assertEqual(self.game.bombs_left, 1)
                # 一度離した後の新しい押下では、通常どおり1発だけ発射できる。
                self.game.handle_gamepad(GamepadInput())
                self.game.handle_gamepad(held)
                self.assertIsNotNone(self.game.bomb)
                self.assertEqual(self.game.bombs_left, 0)
                self.game.bomb = None
                self.game.bombs_left = 1
                self.game.handle_gamepad(GamepadInput(bomb_held=True))
                self.assertIsNone(self.game.bomb)
                self.assertEqual(self.game.bombs_left, 1)

    def test_keyboard_bomb_still_works_while_controller_bomb_is_blocked(self):
        self.game.reset()
        self.game.ready_timer = 0
        self.game.handle_gamepad(GamepadInput(bomb_held=True, actions=("bomb",)))
        self.assertIsNone(self.game.bomb)
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_b))
        self.assertIsNotNone(self.game.bomb)


if __name__ == "__main__":
    unittest.main()
