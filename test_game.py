"""画面を開かずにボム・ゲーム進行を検証する回帰テスト。"""

import os
import random
import unittest
from unittest.mock import Mock, patch
from collections import defaultdict

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from main import (
    Alien, Bomb, Bullet, Explosion, Game, ALIEN_COUNT, ALIEN_ROWS,
    BOMB_RADIUS, BOMB_MIN_SPEED, PATTERN_DURATION, EXPLOSION_DURATION, ENEMY_FIRE,
    SPECIAL_BULLET_SPEED, SPECIAL_BULLET_SWAY, enemy_fire_intervals,
)
from effects import MAX_PARTICLES
from sound import SoundEffects, SOUNDS, synthesize


class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.display.init()
        cls.screen = pygame.display.set_mode((800, 600))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def setUp(self) -> None:
        self.game = Game(self.screen)
        self.game.reset()
        self.game.ready_timer = 0
        self.keys = defaultdict(bool)

    def press_b(self) -> None:
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_b))

    def test_normal_phases_and_tutorial_collide_with_the_visible_ship(self) -> None:
        # 通常弾の幅4・高さ12を含め、翼・機首・透明な角・画像外を確認する。
        for phase in (0, 1, 2, 3):
            for location, dx, dy, hits in (
                ("wing", 2, 15, True),
                ("nose", 16, 0, True),
                ("transparent_corner", 2, 3, False),
                ("outside", -2, 15, False),
            ):
                with self.subTest(phase=phase, location=location):
                    if phase == 0:
                        self.game.start_tutorial()
                    else:
                        self.game.reset(start_phase=phase)
                    rect = self.game.player_rect
                    bullet = Bullet(rect.left + dx, rect.top + dy, 0, False)
                    self.game.bullets = [bullet]
                    self.game.update_bullets(0)
                    self.assertEqual(self.game.lives, 4 if hits else 5)
                    self.assertEqual(bullet not in self.game.bullets, hits)

    def test_extra_keeps_the_small_center_hitbox(self) -> None:
        for location in ("wing", "nose", "center"):
            with self.subTest(location=location):
                self.game.reset(start_phase=4)
                rect = self.game.player_rect
                center = {
                    "wing": (rect.left + 2, rect.top + 15),
                    "nose": (rect.centerx, rect.top),
                    "center": rect.center,
                }[location]
                bullet = Bullet(*center, 0, False)
                self.game.bullets = [bullet]
                self.game.update_bullets(0)
                self.assertEqual(self.game.player_hitbox.size, (6, 6))
                self.assertEqual(self.game.lives, 4 if location == "center" else 5)

    def test_select_start_phase_from_debug(self) -> None:
        for phase, key in ((1, pygame.K_1), (2, pygame.K_2), (3, pygame.K_3)):
            self.game.state = "title"
            self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2))
            self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
            self.assertEqual(self.game.state, "debug")
            self.assertEqual(self.game.start_phase, phase)
            self.game.draw()
            self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
            self.assertEqual(self.game.state, "playing")
            self.assertEqual(self.game.wave, phase)
            self.assertEqual(self.game.bombs_left, phase)
            self.assertEqual(self.game.lives, 5)
            self.assertEqual(self.game.score, 0)

    def test_phase_selection_ignored_during_gameplay_and_pause(self) -> None:
        for state in ("playing", "paused"):
            self.game.state = state
            self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3))
            self.assertEqual(self.game.state, state)
            self.assertEqual(self.game.wave, 1)

    def test_select_and_restart_phase_from_end_screens(self) -> None:
        for state in ("game_over", "victory"):
            self.game.state = state
            self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2))
            self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
            self.assertEqual(self.game.state, "debug")
            self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
            self.assertEqual(self.game.wave, 2)
            self.game.state = state
            self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
            self.assertEqual(self.game.wave, 1)
            self.assertEqual(self.game.state, "playing")

    def test_starting_phase_three_can_clear_directly(self) -> None:
        self.game.state = "title"
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2))
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3))
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.game.ready_timer = 0
        self.game.lives = 2
        self.game.aliens.clear()
        for _ in range(51):
            self.game.update(1 / 60, self.keys)
        self.assertEqual(self.game.state, "victory")
        self.assertEqual(self.game.wave, 3)

    def test_bomb_hits_area_and_preserves_outside_enemies(self) -> None:
        inside = Alien(pygame.Rect(395, 195, 24, 24), 0, 0)
        edge = Alien(pygame.Rect(400 + BOMB_RADIUS, 195, 24, 24), 1, 1)
        outside = Alien(pygame.Rect(400 + BOMB_RADIUS + 1, 195, 24, 24), 3, 2)
        distant_enemy = Alien(pygame.Rect(700, 230, 24, 24), 3, 3)
        extra_enemies = [Alien(pygame.Rect(700, y, 24, 24), 3, column) for column, y in ((4, 270), (5, 310))]
        self.game.aliens = [inside, edge, outside, distant_enemy, *extra_enemies]
        friendly = Bullet(400, 200, -510, True)
        distant = Bullet(700, 200, 200, False)
        self.game.bullets = [friendly, distant, Bullet(400, 200, 200, False)]
        self.game.explode_bomb((400, 200))
        self.assertEqual(self.game.aliens, [outside, distant_enemy, *extra_enemies])
        self.assertEqual(self.game.score, inside.points + edge.points)
        self.assertEqual(self.game.high_score, self.game.score)
        self.assertEqual(self.game.bullets, [friendly, distant])
        score = self.game.score
        self.game.explode_bomb((400, 200))
        self.assertEqual(self.game.score, score)

    def test_bomb_limit_and_no_concurrent_launches(self) -> None:
        self.game.wave = 2
        self.game.prepare_wave()
        self.game.ready_timer = 0
        self.press_b()
        self.assertIsNotNone(self.game.bomb)
        self.assertEqual(self.game.bombs_left, 1)
        self.press_b()
        self.assertEqual(self.game.bombs_left, 1)
        self.game.bomb = None
        self.press_b()
        self.assertEqual(self.game.bombs_left, 0)
        self.game.bomb = None
        self.press_b()
        self.assertIsNone(self.game.bomb)

    def test_bomb_disabled_outside_active_play(self) -> None:
        for state in ("title", "paused", "game_over", "victory"):
            self.game.reset()
            self.game.state = state
            self.press_b()
            self.assertIsNone(self.game.bomb)
        self.game.reset()
        for timer in ("ready_timer", "wave_timer"):
            setattr(self.game, timer, 0.5)
            self.press_b()
            self.assertIsNone(self.game.bomb)
            setattr(self.game, timer, 0)
        self.assertEqual(self.game.bombs_left, 1)

    def test_bomb_ignores_shields_and_detonates_at_top(self) -> None:
        shield_areas = [shield.mask.count() for shield in self.game.shields]
        self.game.player_x = 145
        self.press_b()
        for _ in range(240):
            self.game.update_bomb(1 / 60)
        self.assertIsNone(self.game.bomb)
        self.assertEqual(len(self.game.blasts), 1)
        self.assertEqual(self.game.blasts[0].center, (145, 90))
        self.assertEqual([shield.mask.count() for shield in self.game.shields], shield_areas)
        self.assertEqual(self.game.lives, 5)

    def test_last_enemy_bomb_clear_advances_and_refills(self) -> None:
        self.game.aliens = [Alien(pygame.Rect(390, 180, 24, 24), 0, 0)]
        self.game.bomb = Bomb(400, 190)
        self.game.bombs_left = 0
        self.game.update(1 / 60, self.keys)
        self.assertFalse(self.game.aliens)
        self.assertEqual(self.game.wave_timer, 0)
        self.assertEqual(len(self.game.falling_aliens), 1)
        for _ in range(120):
            self.game.update(1 / 60, self.keys)
        self.assertEqual(self.game.wave, 2)
        self.assertEqual(len(self.game.aliens), 60)
        self.assertEqual(self.game.bombs_left, 2)
        self.assertIsNone(self.game.bomb)
        self.assertFalse(self.game.blasts)

    def test_shot_enemy_tilts_falls_then_explodes(self) -> None:
        alien = Alien(pygame.Rect(400, 150, 24, 24), 0, 0)
        self.game.aliens = [alien]
        self.game.bullets = [Bullet(412, 162, -510, True)]
        self.game.update_bullets(0)
        self.assertFalse(self.game.aliens)
        self.assertFalse(self.game.bullets)
        self.assertEqual(self.game.score, 30)
        self.assertEqual(len(self.game.falling_aliens), 1)
        self.assertFalse(self.game.explosions)
        falling = self.game.falling_aliens[0]
        initial_y = falling.y
        initial_size = falling.image.get_size()
        self.game.update_falling_aliens(0.2)
        self.assertGreater(falling.y, initial_y)
        self.assertNotEqual(falling.image.get_size(), initial_size)
        self.assertFalse(self.game.explosions)
        for _ in range(30):
            self.game.update_falling_aliens(1 / 60)
        self.assertFalse(self.game.falling_aliens)
        self.assertEqual(len(self.game.explosions), 1)
        self.assertGreater(self.game.explosions[0].center[1], initial_y)
        self.assertEqual(self.game.score, 30)

    def test_falling_enemy_causes_chain_kills(self) -> None:
        top = Alien(pygame.Rect(400, 150, 24, 24), 0, 0)
        middle = Alien(pygame.Rect(400, 190, 24, 24), 1, 0)
        bottom = Alien(pygame.Rect(400, 230, 24, 24), 3, 0)
        distant = Alien(pygame.Rect(600, 230, 24, 24), 3, 1)
        self.game.aliens = [top, middle, bottom, distant]
        self.game.down_alien(top)
        for _ in range(120):
            self.game.update_falling_aliens(1 / 60)
        self.assertEqual(self.game.aliens, [distant])
        self.assertEqual(self.game.score, top.points + middle.points + bottom.points)
        self.assertEqual(len(self.game.explosions), 3)
        self.assertFalse(self.game.falling_aliens)

    def test_enemy_explosion_is_visual_only(self) -> None:
        alien = Alien(pygame.Rect(400, 190, 24, 24), 1, 0)
        self.game.aliens = [alien]
        self.game.explosions = [Explosion(alien.rect.center)]
        self.game.update(1 / 60, self.keys)
        self.assertEqual(self.game.aliens, [alien])
        self.assertEqual(self.game.score, 0)
        self.assertFalse(self.game.falling_aliens)
        for _ in range(30):
            self.game.update(1 / 60, self.keys)
        self.assertFalse(self.game.explosions)
        self.assertEqual(self.game.aliens, [alien])

    def test_repeated_kill_does_not_duplicate_score_or_falling_enemy(self) -> None:
        alien = self.game.aliens[0]
        self.game.down_alien(alien)
        self.game.down_alien(alien)
        self.assertEqual(self.game.score, alien.points)
        self.assertEqual(len(self.game.falling_aliens), 1)

    def test_two_falling_enemies_score_collision_target_once(self) -> None:
        target = Alien(pygame.Rect(400, 190, 24, 24), 1, 0)
        self.game.aliens = [target]
        sprite = self.game.alien_images[0][0]
        self.game.start_falling(sprite, (412, 162))
        self.game.start_falling(sprite, (418, 162))
        for _ in range(30):
            self.game.update_falling_aliens(1 / 60)
        self.assertFalse(self.game.aliens)
        self.assertEqual(self.game.score, target.points)

    def test_bomb_kills_also_start_falling(self) -> None:
        aliens = self.game.aliens[:2]
        self.game.aliens = aliens.copy()
        self.game.explode_bomb((250, 120))
        self.assertFalse(self.game.aliens)
        self.assertEqual(len(self.game.falling_aliens), 2)
        self.assertEqual(self.game.score, sum(alien.points for alien in aliens))
        self.assertFalse(self.game.explosions)

    def test_ufo_falls_and_cannot_be_scored_twice(self) -> None:
        self.game.ufo_x = 300
        points = self.game.down_ufo()
        self.assertIn(points, (50, 100, 150, 300))
        self.assertEqual(len(self.game.falling_aliens), 1)
        self.assertEqual(self.game.falling_aliens[0].sprite.get_size(), self.game.ufo_image.get_size())
        self.assertEqual(self.game.down_ufo(), 0)
        self.assertEqual(self.game.score, points)

    def test_pause_freezes_falling_enemies_and_explosions(self) -> None:
        self.game.down_alien(self.game.aliens[0])
        falling = self.game.falling_aliens[0]
        initial_center = falling.center
        self.game.explosions = [Explosion((400, 200))]
        self.game.state = "paused"
        self.game.update(1, self.keys)
        self.assertEqual(falling.age, 0)
        self.assertEqual(falling.center, initial_center)
        self.assertEqual(self.game.explosions[0].remaining, EXPLOSION_DURATION)

    def test_phase_start_clears_falling_enemies_and_explosions(self) -> None:
        self.game.down_alien(self.game.aliens[0])
        self.game.explosions = [Explosion((400, 200))]
        self.game.prepare_wave()
        self.assertFalse(self.game.falling_aliens)
        self.assertFalse(self.game.explosions)

    def test_victory_waits_for_last_enemys_fall_and_explosion(self) -> None:
        self.game.reset(start_phase=3)
        self.game.lives = 2
        self.game.ready_timer = 0
        alien = self.game.aliens[0]
        self.game.aliens = [alien]
        self.game.down_alien(alien)
        self.game.update(0.1, self.keys)
        self.assertEqual(self.game.state, "playing")
        self.assertEqual(self.game.wave_timer, 0)
        for _ in range(120):
            self.game.update(1 / 60, self.keys)
        self.assertEqual(self.game.state, "victory")
        self.assertFalse(self.game.falling_aliens)
        self.assertFalse(self.game.explosions)

    def test_render_falling_enemy_and_explosion(self) -> None:
        self.game.down_alien(self.game.aliens[0])
        self.game.falling_aliens[0].advance(0.2)
        self.game.explosions = [Explosion((400, 200))]
        self.game.draw()

    def test_final_enemy_speed_stays_manageable(self) -> None:
        self.game.aliens = [Alien(pygame.Rect(100, 150, 24, 24), 0, 0)]
        for _ in range(60):
            self.game.move_aliens(1 / 60)
        self.assertLessEqual(self.game.aliens[0].rect.x - 100, 36)
        self.assertGreater(self.game.aliens[0].rect.x, 100)

    def test_bomb_slows_down_without_stopping(self) -> None:
        bomb = Bomb(100, 1000)
        bomb.advance(0.5)
        first_distance = 1000 - bomb.y
        first_speed = bomb.speed
        previous_y = bomb.y
        bomb.advance(0.5)
        self.assertLess(previous_y - bomb.y, first_distance)
        self.assertLess(bomb.speed, first_speed)
        bomb.advance(10)
        self.assertEqual(bomb.speed, BOMB_MIN_SPEED)
        previous_y = bomb.y
        bomb.advance(0.5)
        self.assertLess(bomb.y, previous_y)

    def test_bomb_distance_is_independent_of_frame_rate(self) -> None:
        coarse = Bomb(100, 1000)
        fine = Bomb(100, 1000)
        coarse.advance(3)
        for _ in range(180):
            fine.advance(1 / 60)
        self.assertAlmostEqual(coarse.y, fine.y)
        self.assertAlmostEqual(coarse.speed, fine.speed)

    def test_each_phase_has_its_own_bomb_allowance(self) -> None:
        for phase in (1, 2, 3):
            self.game.wave = phase
            self.game.prepare_wave()
            self.assertEqual(self.game.bombs_left, phase)
            self.game.bombs_left = 0
        self.game.reset()
        self.assertEqual(self.game.bombs_left, 1)

    def test_phase_one_keeps_formation_movement(self) -> None:
        starts = [alien.rect.copy() for alien in self.game.aliens]
        for _ in range(36):
            self.game.move_aliens(1 / 60)
        for alien, start in zip(self.game.aliens, starts):
            self.assertEqual(alien.rect.x - start.x, 12)
            self.assertEqual(alien.rect.y, start.y)
        self.game.aliens = [Alien(pygame.Rect(748, 100, 24, 24), 0, 0)]
        self.game.alien_timer = 1
        self.game.move_aliens(1 / 60)
        self.assertEqual(self.game.direction, -1)
        self.assertEqual(self.game.aliens[0].rect.topleft, (748, 122))

    def test_phase_one_compact_staggered_formation_promotes_chain_kills(self) -> None:
        self.game.reset(start_phase=1)
        top = next(alien for alien in self.game.aliens if alien.row == 0 and alien.column == 4)
        below = [alien for alien in self.game.aliens if alien.row == 1 and alien.column in (3, 4)]
        self.assertEqual([alien.rect.centerx - top.rect.centerx for alien in below], [-18, 18])
        self.assertTrue(all(alien.rect.y - top.rect.y == 32 for alien in below))
        self.game.aliens = [top, *below]
        self.game.down_alien(top)
        self.game.falling_aliens[0].drift = 0
        for _ in range(45):
            self.game.update_falling_aliens(1 / 60)
        self.assertFalse(self.game.aliens)
        self.assertEqual(self.game.score, 70)

    def test_phase_two_layout_is_unchanged(self) -> None:
        self.game.reset(start_phase=2)
        for alien in self.game.aliens:
            self.assertEqual(alien.rect.topleft, (154 + alien.column * 52, 124 + alien.row * 40))
            self.assertEqual(alien.squad, -1)

    def test_phase_two_staggers_rows_and_keeps_each_row_together(self) -> None:
        self.game.wave = 2
        self.game.prepare_wave()
        starts = {id(alien): alien.rect.copy() for alien in self.game.aliens}
        for _ in range(18):
            self.game.move_aliens(1 / 60)
        # 隊列が最初の一歩を踏む前にも、行ごとの逆向きの揺れが見える。
        for alien in self.game.aliens:
            offset = alien.rect.x - starts[id(alien)].x
            if alien.row % 2 == 0:
                self.assertGreater(offset, 0)
            else:
                self.assertLess(offset, 0)
        for row in range(ALIEN_ROWS):
            offsets = {
                alien.rect.x - starts[id(alien)].x
                for alien in self.game.aliens if alien.row == row
            }
            self.assertEqual(len(offsets), 1)
        for _ in range(54):
            self.game.move_aliens(1 / 60)
        # 1.2秒後、全体は12pxずつ2歩進み、各行の揺れは±12px以内。
        for alien in self.game.aliens:
            offset = alien.rect.x - starts[id(alien)].x
            self.assertLessEqual(abs(offset - 24), 12)
            self.assertEqual(alien.rect.y, starts[id(alien)].y)
        self.assertEqual(self.game.movement_pattern, "ROWS")

    def test_phase_two_formation_bounces_and_descends_together(self) -> None:
        self.game.wave = 2
        self.game.prepare_wave()
        start_y = self.game.aliens[0].rect.y
        saw_turn = False
        for _ in range(1800):
            previous_direction = self.game.direction
            self.game.move_aliens(1 / 60)
            saw_turn |= self.game.direction != previous_direction
            for row in range(ALIEN_ROWS):
                members = [alien for alien in self.game.aliens if alien.row == row]
                self.assertEqual(len({alien.rect.y for alien in members}), 1)
                for left, right in zip(members, members[1:]):
                    self.assertEqual(right.rect.x - left.rect.x, 52)
                self.assertGreaterEqual(min(alien.rect.left for alien in members), 28)
                self.assertLessEqual(max(alien.rect.right for alien in members), 772)
                lower = [alien.rect.top for alien in self.game.aliens if alien.row > row]
                if lower:
                    self.assertEqual(min(lower) - members[0].rect.top, 40)
        self.assertTrue(saw_turn)
        self.assertGreater(self.game.aliens[0].rect.y, start_y)

    def test_phase_two_row_sway_repeats_without_drift(self) -> None:
        self.game.wave = 2
        self.game.prepare_wave()
        start_x = self.game.aliens[0].rect.x
        offsets = []
        # 全体の移動がない長い間隔で呼び、横揺れそのものを検証する。
        for frame in range(288):
            self.game.phase_elapsed = (frame + 1) / 60
            self.game.move_rows(1 / 60, interval=100)
            offsets.append(self.game.aliens[0].rect.x - start_x)
        self.assertEqual(min(offsets), -12)
        self.assertEqual(max(offsets), 12)
        self.assertEqual(offsets[143], 0)
        self.assertEqual(offsets[287], 0)

    def test_phase_two_row_sway_holds_then_jumps(self) -> None:
        self.game.wave = 2
        self.game.prepare_wave()
        start_x = self.game.aliens[0].rect.x
        for elapsed, expected_offset in ((0.1, 0), (0.29, 0), (0.31, 6), (0.59, 6), (0.61, 12), (0.91, 6)):
            with self.subTest(elapsed=elapsed):
                self.game.phase_elapsed = elapsed
                self.game.move_rows(1 / 60, interval=100)
                self.assertEqual(self.game.aliens[0].rect.x - start_x, expected_offset)

    def test_phase_two_moves_remaining_rows_after_enemies_are_destroyed(self) -> None:
        self.game.wave = 2
        self.game.prepare_wave()
        self.game.aliens = [alien for alien in self.game.aliens if alien.row == 2 and alien.column % 2 == 0]
        starts = [alien.rect.x for alien in self.game.aliens]
        for _ in range(60):
            self.game.move_aliens(1 / 60)
        self.assertTrue(all(alien.rect.x > x for alien, x in zip(self.game.aliens, starts)))

    def test_phase_three_changes_movement_over_time(self) -> None:
        self.game.wave = 3
        self.game.prepare_wave()
        self.assertEqual(self.game.movement_pattern, "SWAY")
        for expected in ("RUSH", "WEAVE", "SWAY"):
            for _ in range(round(PATTERN_DURATION * 60)):
                self.game.move_aliens(1 / 60)
            # 境界での浮動小数点誤差を避け、切り替え直後を検証する。
            self.game.move_aliens(1 / 60)
            self.assertEqual(self.game.movement_pattern, expected)

    def test_phase_three_squads_keep_their_shapes_and_stay_in_bounds(self) -> None:
        self.game.wave = 3
        self.game.prepare_wave()
        starts = {id(alien): alien.rect.copy() for alien in self.game.aliens}
        maximum_sway = 0
        for _ in range(1200):
            self.game.move_aliens(1 / 60)
            maximum_sway = max(maximum_sway, max(abs(offset) for offset in self.game.row_offsets))
            for squad in range(4):
                members = [alien for alien in self.game.aliens if alien.squad == squad]
                vertical_shifts = {alien.rect.y - starts[id(alien)].y for alien in members}
                self.assertEqual(len(vertical_shifts), 1)
                for row in {alien.row for alien in members}:
                    row_members = [alien for alien in members if alien.row == row]
                    shifts = {alien.rect.x - starts[id(alien)].x for alien in row_members}
                    self.assertEqual(len(shifts), 1)
                    for left, right in zip(row_members, row_members[1:]):
                        self.assertEqual(right.rect.x - left.rect.x, 36)
            self.assertGreaterEqual(min(alien.rect.left for alien in self.game.aliens), 28)
            self.assertLessEqual(max(alien.rect.right for alien in self.game.aliens), 772)
        self.assertEqual(maximum_sway, 18)

    def test_phase_three_has_four_squads_of_fifteen(self) -> None:
        self.game.reset(start_phase=3)
        self.assertEqual({alien.squad for alien in self.game.aliens}, {0, 1, 2, 3})
        for squad in range(4):
            members = [alien for alien in self.game.aliens if alien.squad == squad]
            self.assertEqual(len(members), 15)
            self.assertEqual(len({alien.row for alien in members}), 3)
            self.assertEqual(len({alien.column for alien in members}), 5)
            self.assertEqual(sum(alien.special for alien in members), 3)

    def test_phase_three_squads_approach_at_different_times(self) -> None:
        self.game.reset(start_phase=3)
        starts = {id(alien): alien.rect.copy() for alien in self.game.aliens}
        for _ in range(96):
            self.game.move_aliens(1 / 60)
        vertical_shifts = [
            next(alien.rect.y - starts[id(alien)].y for alien in self.game.aliens if alien.squad == squad)
            for squad in range(4)
        ]
        self.assertGreater(len(set(vertical_shifts)), 1)
        for squad in (0, 1):
            top_bottom = max(alien.rect.bottom for alien in self.game.aliens if alien.squad == squad)
            bottom_top = min(alien.rect.top for alien in self.game.aliens if alien.squad == squad + 2)
            self.assertLess(bottom_top - top_bottom, 92)

    def test_chain_crosses_squad_boundary_only_when_squads_approach(self) -> None:
        for elapsed, should_cross in ((0, False), (1.6, True), (2.4, False)):
            with self.subTest(elapsed=elapsed):
                self.game.reset(start_phase=3)
                for _ in range(round(elapsed * 60)):
                    self.game.move_aliens(1 / 60)
                upper = next(alien for alien in self.game.aliens if alien.row == 2 and alien.column == 2)
                lower = next(alien for alien in self.game.aliens if alien.row == 3 and alien.column == 2)
                self.assertNotEqual(upper.squad, lower.squad)
                self.game.aliens = [upper, lower]
                self.game.down_alien(upper)
                self.game.falling_aliens[0].drift = 0
                for _ in range(45):
                    self.game.move_aliens(1 / 60)
                    self.game.update_falling_aliens(1 / 60)
                self.assertEqual(lower not in self.game.aliens, should_cross)

    def test_pause_and_phase_reset_freeze_and_clear_squad_motion(self) -> None:
        self.game.reset(start_phase=3)
        for _ in range(96):
            self.game.move_aliens(1 / 60)
        positions = [alien.rect.copy() for alien in self.game.aliens]
        elapsed = self.game.squad_elapsed
        self.game.state = "paused"
        self.game.update(1, self.keys)
        self.assertEqual([alien.rect for alien in self.game.aliens], positions)
        self.assertEqual(self.game.squad_elapsed, elapsed)
        self.game.prepare_wave()
        self.assertEqual(self.game.squad_elapsed, 0)
        self.assertEqual(self.game.squad_offsets, [(0, 0)] * 4)

    def test_each_phase_starts_with_sixty_enemies_clear_of_shields(self) -> None:
        for phase in (1, 2, 3):
            self.game.reset(start_phase=phase)
            self.assertEqual(len(self.game.aliens), 60)
            self.assertEqual(ALIEN_COUNT, 60)
            for alien in self.game.aliens:
                self.assertFalse(any(alien.rect.colliderect(shield.rect) for shield in self.game.shields))

    def test_enemy_fire_grows_in_frequency_and_salvo_with_constant_speed(self) -> None:
        shot_counts = []
        speeds = []
        for phase in (1, 2, 3):
            self.game.reset(start_phase=phase)
            for alien in self.game.aliens:
                alien.special = False
            self.game.enemy_shot_timer = 0
            self.game.player_x = 700
            self.game.update_enemy_fire(0)
            self.assertEqual(len(self.game.bullets), phase)
            self.assertEqual(len({bullet.x for bullet in self.game.bullets}), phase)
            speeds.append(self.game.bullets[0].velocity)
            self.assertTrue(all(bullet.velocity == 180 for bullet in self.game.bullets))
            self.assertTrue(all(bullet.horizontal_velocity == 0 for bullet in self.game.bullets))
            count = len(self.game.bullets)
            self.game.bullets.clear()
            for _ in range(120):
                self.game.update_enemy_fire(1 / 60)
                count += len(self.game.bullets)
                self.game.bullets.clear()
            shot_counts.append(count)
        self.assertLess(shot_counts[0], shot_counts[1])
        self.assertLess(shot_counts[1], shot_counts[2])
        self.assertEqual(speeds, [180, 180, 180])

    def test_enemy_fire_obeys_limits_and_front_line(self) -> None:
        for phase, fire in enumerate(ENEMY_FIRE, start=1):
            self.game.reset(start_phase=phase)
            self.game.enemy_shot_timer = 0
            self.game.update_enemy_fire(0)
            front_y = max(alien.rect.bottom for alien in self.game.aliens)
            self.assertTrue(all(bullet.y == front_y + 8 for bullet in self.game.bullets))
            self.game.bullets = [Bullet(100 + i, 400, fire.speed, False) for i in range(fire.limit - 1)]
            self.game.enemy_shot_timer = 0
            self.game.update_enemy_fire(0)
            self.assertEqual(len(self.game.bullets), fire.limit)
            self.game.enemy_shot_timer = 0
            self.game.update_enemy_fire(0)
            self.assertEqual(len(self.game.bullets), fire.limit)

    def test_eight_or_more_enemies_keep_normal_fire_intervals(self) -> None:
        for phase, fire in enumerate(ENEMY_FIRE, start=1):
            for count in (8, 9, 30, 60):
                with self.subTest(phase=phase, count=count):
                    bounds = enemy_fire_intervals(phase, count)
                    self.assertAlmostEqual(bounds[0], fire.interval_min)
                    self.assertAlmostEqual(bounds[1], fire.interval_max)

    def test_fire_rates_decrease_linearly_below_eight_enemies(self) -> None:
        for phase, fire in enumerate(ENEMY_FIRE, start=1):
            bounds = [enemy_fire_intervals(phase, count) for count in range(8, 0, -1)]
            for index, (base, final) in enumerate(((fire.interval_min, 1.8), (fire.interval_max, 2.4))):
                with self.subTest(phase=phase, bound=index):
                    rates = [1 / pair[index] for pair in bounds]
                    expected_step = (1 / base - 1 / final) / 7
                    for before, after in zip(rates, rates[1:]):
                        self.assertGreater(before, after)
                        self.assertAlmostEqual(before - after, expected_step)
                    self.assertAlmostEqual(bounds[-1][index], final)

    def test_firing_uses_intervals_for_current_enemy_count(self) -> None:
        for phase, fire in enumerate(ENEMY_FIRE, start=1):
            for count in (8, 7, 4, 3, 2, 1):
                with self.subTest(phase=phase, count=count):
                    self.game.reset(start_phase=phase)
                    self.game.aliens = [alien for alien in self.game.aliens if not alien.special][:count]
                    self.game.enemy_shot_timer = 0
                    with patch("main.random.uniform", side_effect=lambda low, high: (low + high) / 2):
                        self.game.update_enemy_fire(0)
                    low, high = enemy_fire_intervals(phase, count)
                    self.assertAlmostEqual(self.game.enemy_shot_timer, (low + high) / 2)
                    self.assertEqual(len(self.game.bullets), min(fire.salvo, count))
                    self.assertTrue(all(bullet.velocity == fire.speed for bullet in self.game.bullets))

    def test_kills_gradually_stretch_pending_fire_without_clearing_bullets(self) -> None:
        for phase, fire in enumerate(ENEMY_FIRE, start=1):
            with self.subTest(phase=phase):
                self.game.reset(start_phase=phase)
                self.game.aliens = self.game.aliens[:9]
                friendly = Bullet(400, 500, -510, True)
                hostile = Bullet(100, 400, fire.speed, False)
                self.game.bullets = [friendly, hostile]
                self.game.enemy_shot_timer = fire.interval_min / 2
                for count in range(8, 0, -1):
                    previous_timer = self.game.enemy_shot_timer
                    self.game.down_alien(self.game.aliens[0])
                    interval_min, _ = enemy_fire_intervals(phase, count)
                    self.assertAlmostEqual(self.game.enemy_shot_timer, interval_min / 2)
                    self.assertEqual(self.game.bullets, [friendly, hostile])
                    self.assertEqual(hostile.velocity, fire.speed)
                    if count == 8:
                        self.assertAlmostEqual(self.game.enemy_shot_timer, previous_timer)
                    else:
                        self.assertGreater(self.game.enemy_shot_timer, previous_timer)
                self.game.prepare_wave()
                self.assertGreaterEqual(self.game.enemy_shot_timer, fire.interval_min)
                self.assertLessEqual(self.game.enemy_shot_timer, fire.interval_max)

    def test_last_enemy_fires_at_normal_speed_with_long_gaps(self) -> None:
        for phase, fire in enumerate(ENEMY_FIRE, start=1):
            with self.subTest(phase=phase):
                self.game.reset(start_phase=phase)
                self.game.aliens = self.game.aliens[:1]
                self.game.enemy_shot_timer = 0
                self.game.update_enemy_fire(0)
                self.assertEqual(len(self.game.bullets), 1)
                self.assertEqual(self.game.bullets[0].velocity, fire.speed)
                self.assertGreaterEqual(self.game.enemy_shot_timer, 1.8)
                self.assertLessEqual(self.game.enemy_shot_timer, 2.4)
                self.game.bullets.clear()
                self.game.update_enemy_fire(1.5)
                self.assertFalse(self.game.bullets)
                self.game.update_enemy_fire(0.91)
                self.assertEqual(len(self.game.bullets), 1)

    def test_few_enemies_keep_phase_bullet_limits_and_special_volleys(self) -> None:
        for phase, fire in enumerate(ENEMY_FIRE, start=1):
            self.game.reset(start_phase=phase)
            self.game.aliens = self.game.aliens[:3]
            self.game.bullets = [Bullet(100, 400, fire.speed, False) for _ in range(fire.limit - 1)]
            self.game.enemy_shot_timer = 0
            self.game.update_enemy_fire(0)
            self.assertEqual(len(self.game.bullets), fire.limit)
        self.game.reset(start_phase=3)
        self.game.aliens = [alien for alien in self.game.aliens if alien.special][:3]
        self.game.enemy_shot_timer = 0
        self.game.update_enemy_fire(0)
        self.assertEqual(len(self.game.bullets), 9)
        self.assertTrue(all(bullet.curve_amplitude for bullet in self.game.bullets))
        self.assertTrue(all(bullet.velocity == 108 for bullet in self.game.bullets))

    def test_phase_three_starts_farther_from_player_and_squads_bob_inward(self) -> None:
        self.game.reset(start_phase=3)
        bottom = max(alien.rect.bottom for alien in self.game.aliens)
        self.assertEqual(bottom, 348)
        self.assertGreaterEqual(self.game.player_rect.top - bottom, 190)
        descent = 0
        for _ in range(1200):
            direction = self.game.direction
            self.game.move_aliens(1 / 60)
            if self.game.direction != direction:
                descent += 12
            self.assertLessEqual(max(alien.rect.bottom for alien in self.game.aliens), bottom + descent)
            self.assertTrue(all(offset[1] >= 0 for offset in self.game.squad_offsets[:2]))
            self.assertTrue(all(offset[1] <= 0 for offset in self.game.squad_offsets[2:]))

    def test_phase_three_descends_in_smaller_steps(self) -> None:
        self.game.reset(start_phase=3)
        for alien in self.game.aliens:
            alien.rect.x += 94
        starts = [alien.rect.y for alien in self.game.aliens]
        self.game.alien_timer = 1
        self.game.move_aliens(0)
        self.assertEqual(self.game.direction, -1)
        self.assertTrue(all(alien.rect.y - start == 12 for alien, start in zip(self.game.aliens, starts)))

    def test_bullet_moves_sideways_and_leaves_screen(self) -> None:
        bullet = Bullet(400, 400, 300, False, 100)
        self.game.bullets = [bullet]
        self.game.update_bullets(0.1)
        self.assertAlmostEqual(bullet.x, 410)
        bullet.x = 900
        self.game.update_bullets(0)
        self.assertFalse(self.game.bullets)

    def test_special_enemies_appear_only_in_phase_three(self) -> None:
        for phase in (1, 2, 3):
            self.game.reset(start_phase=phase)
            specials = [alien for alien in self.game.aliens if alien.special]
            self.assertEqual(len(specials), 12 if phase == 3 else 0)
            if phase == 3:
                for row in range(ALIEN_ROWS):
                    self.assertEqual(sum(alien.row == row for alien in specials), 2)

    def test_special_enemies_attack_three_turns_then_rest_two(self) -> None:
        self.game.reset(start_phase=3)
        attacks = []
        for _ in range(10):
            self.game.bullets.clear()
            self.game.enemy_shot_timer = 0
            self.game.update_enemy_fire(0)
            attacks.append(any(bullet.curve_amplitude for bullet in self.game.bullets))
            self.assertTrue(self.game.bullets)  # 通常敵は休止ターンでも撃てる。
            self.assertEqual(self.game.special_resting, not attacks[-1])
        self.assertEqual(attacks, [True, True, True, False, False] * 2)

    def test_resting_special_enemies_do_not_fire_straight_shots_instead(self) -> None:
        self.game.reset(start_phase=3)
        self.game.aliens = [alien for alien in self.game.aliens if alien.special][:4]
        self.game.special_fire_turn = 3
        for _ in range(2):
            self.game.enemy_shot_timer = 0
            self.game.update_enemy_fire(0)
            self.assertFalse(self.game.bullets)
            self.assertTrue(self.game.special_resting)
        self.game.enemy_shot_timer = 0
        self.game.update_enemy_fire(0)
        self.assertTrue(any(bullet.curve_amplitude for bullet in self.game.bullets))
        self.assertFalse(self.game.special_resting)

    def test_attack_cycle_freezes_during_pause_and_resets_with_phase(self) -> None:
        self.game.reset(start_phase=3)
        self.game.special_fire_turn = 4
        self.game.special_resting = True
        self.game.state = "paused"
        self.game.update(10, self.keys)
        self.assertEqual(self.game.special_fire_turn, 4)
        self.game.prepare_wave()
        self.assertEqual(self.game.special_fire_turn, 0)
        self.assertFalse(self.game.special_resting)

    def test_combo_counts_origin_and_collision_kills_once(self) -> None:
        top = Alien(pygame.Rect(400, 150, 24, 24), 0, 0)
        middle = Alien(pygame.Rect(400, 190, 24, 24), 1, 0)
        bottom = Alien(pygame.Rect(400, 230, 24, 24), 3, 0)
        self.game.aliens = [top, middle, bottom]
        self.game.down_alien(top)
        self.assertEqual(self.game.combo_count, 0)
        chain = self.game.falling_aliens[0].chain
        for _ in range(120):
            self.game.update_falling_aliens(1 / 60)
        self.assertEqual(chain.kills, 3)
        self.assertEqual(chain.collision_kills, 2)
        self.assertEqual(self.game.combo_count, 3)
        self.assertGreater(self.game.combo_timer, 0)
        self.game.down_alien(bottom, chain=chain, collision=True)
        self.assertEqual(chain.kills, 3)

    def test_unrelated_shots_do_not_merge_combo_counts(self) -> None:
        roots = [Alien(pygame.Rect(x, 150, 24, 24), 0, index) for index, x in enumerate((200, 600))]
        targets = [Alien(pygame.Rect(x, 190, 24, 24), 1, index) for index, x in enumerate((200, 600))]
        self.game.aliens = [*roots, *targets]
        for root in roots:
            self.game.down_alien(root)
        chains = [falling.chain for falling in self.game.falling_aliens]
        for _ in range(120):
            self.game.update_falling_aliens(1 / 60)
        self.assertIsNot(chains[0], chains[1])
        self.assertEqual([chain.kills for chain in chains], [2, 2])
        self.assertEqual(self.game.combo_count, 2)

    def test_bomb_chain_shares_count_but_needs_collision_to_show_combo(self) -> None:
        root = Alien(pygame.Rect(400, 240, 24, 24), 1, 0)
        target = Alien(pygame.Rect(400, 280, 24, 24), 3, 0)
        self.game.aliens = [root, target]
        self.game.explode_bomb((400, 150))
        self.assertEqual(self.game.combo_count, 0)
        self.assertEqual(self.game.aliens, [target])
        for _ in range(90):
            self.game.update_falling_aliens(1 / 60)
        self.assertEqual(self.game.combo_count, 2)

    def test_combo_timer_pauses_expires_and_resets(self) -> None:
        top = Alien(pygame.Rect(400, 150, 24, 24), 0, 0)
        below = Alien(pygame.Rect(400, 190, 24, 24), 1, 0)
        self.game.aliens = [top, below]
        self.game.down_alien(top)
        self.game.update_falling_aliens(0.3)
        self.assertEqual(self.game.combo_count, 2)
        timer = self.game.combo_timer
        self.game.state = "paused"
        self.game.update(5, self.keys)
        self.assertEqual(self.game.combo_timer, timer)
        self.game.state = "playing"
        self.game.update(2.1, self.keys)
        self.assertEqual(self.game.combo_timer, 0)
        self.game.prepare_wave()
        self.assertEqual(self.game.combo_count, 0)
        self.assertIsNone(self.game.combo_chain)

    def test_sound_events_are_connected_to_shots_and_bombs(self) -> None:
        sounds = Mock(spec=SoundEffects)
        self.game.sounds = sounds
        self.game.fire()
        sounds.play.assert_any_call("shoot")
        self.game.launch_bomb()
        sounds.play.assert_any_call("bomb_launch")
        self.game.explode_bomb((400, 200))
        sounds.play.assert_any_call("bomb_explosion")
        sounds.play.assert_any_call("hit")

    def test_m_key_toggles_sound(self) -> None:
        self.assertFalse(self.game.sounds.muted)
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m))
        self.assertTrue(self.game.sounds.muted)
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m))
        self.assertFalse(self.game.sounds.muted)

    def test_audio_device_failure_keeps_sound_optional(self) -> None:
        with patch("pygame.mixer.get_init", return_value=None), patch(
            "pygame.mixer.init", side_effect=pygame.error("no audio device"),
        ):
            sounds = SoundEffects()
        self.assertFalse(sounds.enabled)
        sounds.play("shoot")
        sounds.pause(True)
        sounds.toggle_mute()

    def test_missing_mixer_keeps_sound_optional(self) -> None:
        with patch(
            "sound.importlib.import_module", side_effect=ImportError("no pygame mixer"),
        ):
            sounds = SoundEffects()
        self.assertFalse(sounds.enabled)
        sounds.play("shoot")
        sounds.pause(True)
        sounds.toggle_mute()

    def test_sound_synthesis_produces_pcm_without_changing_game_randomness(self) -> None:
        state = random.getstate()
        spec = SOUNDS["shoot"]
        samples = synthesize(spec, 22050, 2)
        self.assertEqual(len(samples), round(22050 * spec.duration) * 2 * 2)
        self.assertTrue(any(samples))
        self.assertEqual(random.getstate(), state)

    def test_special_enemies_fire_three_slow_curved_bullets(self) -> None:
        self.game.reset(start_phase=3)
        special = next(alien for alien in self.game.aliens if alien.special and alien.row == 5)
        normal = next(alien for alien in self.game.aliens if not alien.special and alien.row == 5)
        behind = [alien for alien in self.game.aliens if alien.row == 0 and alien.column in (special.column, normal.column)]
        self.game.aliens = [special, normal, *behind]
        self.game.enemy_shot_timer = 0
        self.game.update_enemy_fire(0)
        curved = [bullet for bullet in self.game.bullets if bullet.curve_amplitude]
        straight = [bullet for bullet in self.game.bullets if not bullet.curve_amplitude]
        self.assertEqual(len(curved), 3)
        self.assertEqual(len(straight), 1)
        self.assertEqual({bullet.horizontal_velocity for bullet in curved}, {-28, 0, 28})
        self.assertTrue(all(bullet.velocity == 108 for bullet in curved))
        self.assertLess(SPECIAL_BULLET_SPEED, straight[0].velocity)

    def test_curved_bullets_sway_and_return_after_a_full_period(self) -> None:
        bullet = Bullet(400, 150, 120, False, curve_amplitude=SPECIAL_BULLET_SWAY)
        positions = []
        for _ in range(144):
            bullet.advance(1 / 60)
            positions.append(bullet.x)
        self.assertAlmostEqual(min(positions), 378)
        self.assertAlmostEqual(max(positions), 422)
        self.assertAlmostEqual(bullet.x, 400)
        self.assertAlmostEqual(bullet.y, 438)

    def test_curved_bullet_motion_does_not_depend_on_frame_rate(self) -> None:
        coarse = Bullet(400, 150, 120, False, -28, 22, 0.7)
        fine = Bullet(400, 150, 120, False, -28, 22, 0.7)
        coarse.advance(1.1)
        for _ in range(66):
            fine.advance(1 / 60)
        self.assertAlmostEqual(coarse.x, fine.x)
        self.assertAlmostEqual(coarse.y, fine.y)

    def test_phase_three_shots_do_not_track_player_position(self) -> None:
        self.game.reset(start_phase=3)
        random_state = random.getstate()
        patterns = []
        try:
            for player_x in (100, 700):
                random.setstate(random_state)
                self.game.player_x = player_x
                self.game.bullets.clear()
                self.game.enemy_shot_timer = 0
                self.game.update_enemy_fire(0)
                patterns.append([
                    (bullet.x, bullet.y, bullet.velocity, bullet.horizontal_velocity, bullet.curve_amplitude, bullet.curve_phase)
                    for bullet in self.game.bullets
                ])
        finally:
            random.setstate(random_state)
        self.assertEqual(patterns[0], patterns[1])

    def test_special_volley_respects_remaining_enemy_bullet_capacity(self) -> None:
        self.game.reset(start_phase=3)
        limit = ENEMY_FIRE[2].limit
        self.game.bullets = [Bullet(100 + index, 400, 270, False) for index in range(limit - 1)]
        self.game.enemy_shot_timer = 0
        self.game.update_enemy_fire(0)
        self.assertEqual(len(self.game.bullets), limit)
        self.assertEqual(sum(bool(bullet.curve_amplitude) for bullet in self.game.bullets), 1)

    def test_last_special_enemy_keeps_curved_volley_speed_and_rest_cycle(self) -> None:
        self.game.reset(start_phase=3)
        special = next(alien for alien in self.game.aliens if alien.special)
        self.game.aliens = [special]
        for turn in range(10):
            self.game.bullets.clear()
            self.game.enemy_shot_timer = 0
            self.game.update_enemy_fire(0)
            self.assertEqual(len(self.game.bullets), 3 if turn % 5 < 3 else 0)
            self.assertTrue(all(bullet.curve_amplitude for bullet in self.game.bullets))
            self.assertTrue(all(bullet.velocity == 108 for bullet in self.game.bullets))
            self.assertGreaterEqual(self.game.enemy_shot_timer, 1.8)
            self.assertLessEqual(self.game.enemy_shot_timer, 2.4)

    def test_curved_bullets_collide_with_shields_and_player(self) -> None:
        self.game.bullets = [Bullet(315, 455, 120, False, curve_amplitude=22)]
        shield_area = self.game.shields[1].mask.count()
        self.game.update_bullets(0)
        self.assertFalse(self.game.bullets)
        self.assertLess(self.game.shields[1].mask.count(), shield_area)
        self.game.bullets = [Bullet(self.game.player_x, self.game.player_rect.centery, 120, False, curve_amplitude=22)]
        self.game.update_bullets(0)
        self.assertEqual(self.game.lives, 4)
        self.assertFalse(self.game.bullets)

    def test_bomb_erases_curved_bullets_within_its_radius(self) -> None:
        self.game.bullets = [
            Bullet(400, 400, 120, False, curve_amplitude=22),
            Bullet(700, 400, 120, False, curve_amplitude=22),
        ]
        self.game.explode_bomb((400, 400))
        self.assertEqual(len(self.game.bullets), 1)
        self.assertEqual(self.game.bullets[0].x, 700)

    def test_smoke_and_sparks_are_visual_and_expire(self) -> None:
        alien = self.game.aliens[0]
        self.game.effects.explode(alien.rect.center)
        self.assertTrue(any(particle.smoke for particle in self.game.effects.particles))
        self.assertTrue(any(not particle.smoke for particle in self.game.effects.particles))
        self.game.update(1 / 60, self.keys)
        self.assertEqual(len(self.game.aliens), 60)
        self.assertEqual(self.game.score, 0)
        self.game.draw()
        self.game.effects.update(2)
        self.assertFalse(self.game.effects.particles)

    def test_falling_and_explosion_emit_smoke(self) -> None:
        alien = self.game.aliens[0]
        self.game.aliens = [alien]
        self.game.down_alien(alien)
        initial = len(self.game.effects.particles)
        self.game.update_falling_aliens(0.2)
        self.assertGreater(len(self.game.effects.particles), initial)
        for _ in range(30):
            self.game.update_falling_aliens(1 / 60)
        self.assertTrue(self.game.explosions)
        self.assertTrue(any(particle.smoke for particle in self.game.effects.particles))

    def test_particle_limit_pause_and_reset(self) -> None:
        for _ in range(50):
            self.game.effects.explode((400, 200))
        self.assertLessEqual(len(self.game.effects.particles), MAX_PARTICLES)
        particle = self.game.effects.particles[0]
        before = (particle.x, particle.y, particle.remaining)
        self.game.state = "paused"
        self.game.update(1, self.keys)
        self.assertEqual((particle.x, particle.y, particle.remaining), before)
        self.game.prepare_wave()
        self.assertFalse(self.game.effects.particles)

    def test_three_phase_completion_stops_and_can_restart(self) -> None:
        self.game.add_score(123)
        self.game.lives = 2
        for phase in (1, 2, 3):
            self.assertEqual(self.game.wave, phase)
            self.game.ready_timer = 0
            self.game.aliens.clear()
            self.game.update(1 / 60, self.keys)
            for _ in range(50):
                self.game.update(1 / 60, self.keys)
        self.assertEqual(self.game.state, "victory")
        self.game.update(10, self.keys)
        self.assertEqual(self.game.wave, 3)
        self.assertEqual(self.game.score, 123)
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertEqual(self.game.state, "playing")
        self.assertEqual(self.game.wave, 1)
        self.assertEqual(self.game.bombs_left, 1)
        self.assertEqual(self.game.score, 0)
        self.assertEqual(self.game.high_score, 123)

    def test_phases_one_and_two_fire_single_shots(self) -> None:
        for phase in (1, 2):
            with self.subTest(phase=phase):
                self.game.wave = phase
                self.game.prepare_wave()
                self.game.shot_timer = 0
                self.game.fire()
                self.assertEqual(len(self.game.bullets), 1)
                self.assertEqual(self.game.bullets[0].x, self.game.player_x)
                self.game.fire()
                self.assertEqual(len(self.game.bullets), 1)
                self.game.shot_timer = 0
                self.game.fire()
                self.assertEqual(len(self.game.bullets), 2)
                self.game.shot_timer = 0
                self.game.fire()
                self.assertEqual(len(self.game.bullets), 2)

    def test_phase_three_alternates_barrels_with_cooldown_and_limit(self) -> None:
        self.game.wave = 3
        self.game.prepare_wave()
        self.game.fire()
        self.assertEqual(len(self.game.bullets), 1)
        self.assertLess(self.game.bullets[0].x, self.game.player_x)
        self.game.fire()
        self.assertEqual(len(self.game.bullets), 1)
        for _ in range(3):
            self.game.shot_timer = 0
            self.game.fire()
        offsets = [bullet.x - self.game.player_x for bullet in self.game.bullets]
        self.assertEqual(offsets, [-9, 9, -9, 9])
        self.game.shot_timer = 0
        self.game.fire()
        self.assertEqual(len(self.game.bullets), 4)
        # 上限で撃てなかった際に砲の順序を飛ばさない。
        self.game.bullets.clear()
        self.game.fire()
        self.assertLess(self.game.bullets[0].x, self.game.player_x)

    def test_phase_three_doubles_rate_and_preserves_each_barrels_rate(self) -> None:
        shots_by_phase = {}
        for phase in (1, 2, 3):
            self.game.reset()
            self.game.wave = phase
            self.game.prepare_wave()
            self.game.ready_timer = 0
            self.keys[pygame.K_SPACE] = True
            shots = []
            for frame in range(60):
                self.game.update(1 / 60, self.keys)
                shots.extend(
                    (frame, bullet.x - self.game.player_x)
                    for bullet in self.game.bullets if bullet.friendly
                )
                # 弾数上限に達しない状態で、入力からの発射間隔を比較する。
                self.game.bullets.clear()
            shots_by_phase[phase] = shots
        single = shots_by_phase[1]
        twin = shots_by_phase[3]
        self.assertEqual(len(shots_by_phase[2]), len(single))
        self.assertEqual(len(twin), len(single) * 2)
        single_intervals = [b[0] - a[0] for a, b in zip(single, single[1:])]
        for offset in (-9, 9):
            barrel_shots = [frame for frame, x in twin if x == offset]
            intervals = [b - a for a, b in zip(barrel_shots, barrel_shots[1:])]
            self.assertEqual(intervals, single_intervals)

    def test_phase_start_resets_alternating_barrel(self) -> None:
        self.game.wave = 3
        self.game.prepare_wave()
        self.game.fire()
        self.game.prepare_wave()
        self.game.fire()
        self.assertEqual(len(self.game.bullets), 1)
        self.assertLess(self.game.bullets[0].x, self.game.player_x)

    def test_pause_freezes_projectile_and_blast(self) -> None:
        self.press_b()
        self.game.explode_bomb((700, 350))
        self.game.state = "paused"
        bomb_y = self.game.bomb.y
        speed = self.game.bomb.speed
        elapsed = self.game.phase_elapsed
        lifetime = self.game.blasts[0].remaining
        self.game.update(1, self.keys)
        self.assertEqual(self.game.bomb.y, bomb_y)
        self.assertEqual(self.game.bomb.speed, speed)
        self.assertEqual(self.game.phase_elapsed, elapsed)
        self.assertEqual(self.game.blasts[0].remaining, lifetime)

    def test_render_states_and_bomb_effect(self) -> None:
        self.press_b()
        self.game.explode_bomb((400, 250))
        for state in ("title", "playing", "paused", "game_over", "victory"):
            self.game.state = state
            self.game.draw()
        self.assertEqual(self.screen.get_size(), (800, 600))


if __name__ == "__main__":
    unittest.main()
