"""EXTRA突入、ボスの耐久力、ビームの予告と即死判定を検証する。"""

import os
import math
import unittest
from collections import defaultdict
from unittest.mock import Mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from main import Bomb, Bullet, Game, PLAYER_Y, EXTRA_PLAYER_TOP, EXTRA_PLAYER_BOTTOM
from extra_stage import (
    BOSS_MAX_HP, BOSS_BOMB_DAMAGE, BOSS_COLLISION_DAMAGE,
    BEAM_WARNING_TIME, BEAM_FIRE_TIME, BEAM_WIDTH,
    BEAM_EXTENSION_SPEED, EXTRA_BULLET_LIMIT, BARRAGE_VOLLEYS_PER_PATTERN, Boss, BeamCannon,
)
from sound import SoundEffects


class ExtraStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.display.init()
        cls.screen = pygame.display.set_mode((800, 600))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def setUp(self) -> None:
        self.game = Game(self.screen)
        self.game.reset(start_phase=4)
        self.game.ready_timer = 0
        self.keys = defaultdict(bool)

    def begin_warning(self):
        cannon = next(iter(self.game.extra_stage.cannons.values()))
        cannon.timer = 0
        self.game.update_extra_stage(0)
        self.assertEqual(cannon.state, "warning")
        return cannon

    def test_phase_three_enters_extra_only_with_three_or_more_lives(self) -> None:
        for lives in range(1, 6):
            with self.subTest(lives=lives):
                self.game.reset(start_phase=3)
                self.game.add_score(1234)
                self.game.lives = lives
                self.game.ready_timer = 0
                self.game.aliens.clear()
                self.game.update(0, self.keys)
                self.game.update(0.81, self.keys)
                if lives >= 3:
                    self.assertEqual(self.game.state, "playing")
                    self.assertIsNotNone(self.game.extra_stage)
                    self.assertEqual(self.game.lives, 5)
                    self.assertFalse(self.game.shields)
                    self.assertFalse(self.game.bullets)
                    self.assertEqual(self.game.bombs_left, 3)
                    self.assertEqual(self.game.extra_stage.boss.hp, BOSS_MAX_HP)
                else:
                    self.assertEqual(self.game.state, "victory")
                    self.assertIsNone(self.game.extra_stage)
                self.assertEqual(self.game.score, 1234)

    def test_game_over_does_not_unlock_extra(self) -> None:
        self.game.reset(start_phase=3)
        self.game.state = "game_over"
        self.game.lives = 3
        self.game.aliens.clear()
        self.game.update(10, self.keys)
        self.assertEqual(self.game.state, "game_over")
        self.assertIsNone(self.game.extra_stage)

    def test_extra_has_ten_escorts_and_exactly_two_cannons_around_large_boss(self) -> None:
        boss = self.game.extra_stage.boss
        self.assertEqual(boss.rect.centerx, 400)
        self.assertEqual(boss.hp, 240)
        self.assertGreater(boss.rect.width, self.game.aliens[0].rect.width * 4)
        self.assertEqual(len(self.game.aliens), 10)
        self.assertEqual(sum(alien.beam_cannon for alien in self.game.aliens), 2)
        self.assertTrue(all(not alien.rect.colliderect(boss.rect) for alien in self.game.aliens))
        self.assertTrue(any(alien.rect.centerx < boss.rect.left for alien in self.game.aliens))
        self.assertTrue(any(alien.rect.centerx > boss.rect.right for alien in self.game.aliens))

    def test_menu_four_selects_extra_and_can_return_to_normal_game(self) -> None:
        self.game.state = "title"
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2))
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4))
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertEqual(self.game.start_phase, 4)
        self.assertIsNotNone(self.game.extra_stage)
        self.assertFalse(self.game.shields)
        self.game.state = "victory"
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2))
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))
        self.game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertIsNone(self.game.extra_stage)
        self.assertEqual(self.game.wave, 1)
        self.assertEqual(len(self.game.aliens), 60)
        self.assertEqual(len(self.game.shields), 4)

    def test_extra_auto_fire_matches_phase_three_with_or_without_space(self) -> None:
        recordings = []
        for phase, space_pressed in ((3, True), (4, False), (4, True)):
            self.game.reset(start_phase=phase)
            self.game.ready_timer = 0
            keys = defaultdict(bool, {pygame.K_SPACE: space_pressed})
            shots = []
            for frame in range(60):
                self.game.update(1 / 60, keys)
                shots.extend(
                    (frame, bullet.x - self.game.player_x)
                    for bullet in self.game.bullets if bullet.friendly
                )
                self.game.bullets.clear()
            recordings.append(shots)
        self.assertTrue(recordings[0])
        self.assertEqual(recordings[0], recordings[1])
        self.assertEqual(recordings[0], recordings[2])
        self.assertEqual([offset for _, offset in recordings[1]], [-9, 9] * (len(recordings[1]) // 2))

    def test_auto_fire_waits_for_intro_and_stops_when_paused_or_boss_defeated(self) -> None:
        self.game.ready_timer = 1
        self.game.update(0.1, self.keys)
        self.assertFalse(self.game.bullets)
        self.game.ready_timer = 0
        self.game.state = "paused"
        self.game.update(1, self.keys)
        self.assertFalse(self.game.bullets)
        self.game.state = "playing"
        self.game.update(0, self.keys)
        self.assertEqual(sum(bullet.friendly for bullet in self.game.bullets), 1)
        self.game.damage_boss(BOSS_MAX_HP)
        self.game.bullets.clear()
        self.game.update(0.5, self.keys)
        self.assertFalse(self.game.bullets)

    def test_extra_supports_wasd_and_arrow_movement_on_both_axes(self) -> None:
        for key, dx, dy in (
            (pygame.K_w, 0, -18), (pygame.K_s, 0, 18),
            (pygame.K_a, -18, 0), (pygame.K_d, 18, 0),
            (pygame.K_UP, 0, -18), (pygame.K_DOWN, 0, 18),
            (pygame.K_LEFT, -18, 0), (pygame.K_RIGHT, 18, 0),
        ):
            with self.subTest(key=key):
                self.game.reset(start_phase=4)
                self.game.ready_timer = 0
                self.game.player_y = 400
                self.game.update(0.1, defaultdict(bool, {key: True}))
                self.assertAlmostEqual(self.game.player_x, 400 + dx)
                self.assertAlmostEqual(self.game.player_y, 400 + dy)
                self.assertEqual(self.game.player_rect.top, round(self.game.player_y))
                self.assertEqual(self.game.player_hitbox.center, self.game.player_rect.center)

    def test_extra_diagonal_speed_is_normalized_and_shift_slows_both_axes(self) -> None:
        for shift, speed in ((None, 180), (pygame.K_LSHIFT, 90), (pygame.K_RSHIFT, 90)):
            self.game.reset(start_phase=4)
            self.game.ready_timer = 0
            self.game.player_y = 400
            keys = defaultdict(bool, {pygame.K_w: True, pygame.K_d: True})
            if shift is not None:
                keys[shift] = True
            self.game.update(0.1, keys)
            dx, dy = self.game.player_x - 400, self.game.player_y - 400
            self.assertAlmostEqual(math.hypot(dx, dy), speed * 0.1)
            self.assertAlmostEqual(dx, -dy)

    def test_extra_vertical_limits_and_return_to_normal_height(self) -> None:
        for key, start_y, expected in (
            (pygame.K_w, EXTRA_PLAYER_TOP + 1, EXTRA_PLAYER_TOP),
            (pygame.K_s, EXTRA_PLAYER_BOTTOM - 22, EXTRA_PLAYER_BOTTOM - 21),
        ):
            self.game.reset(start_phase=4)
            self.game.ready_timer = 0
            self.game.player_y = start_y
            self.game.update(0.1, defaultdict(bool, {key: True}))
            self.assertEqual(self.game.player_y, expected)
            self.assertGreaterEqual(self.game.player_rect.top, EXTRA_PLAYER_TOP)
            self.assertLessEqual(self.game.player_rect.bottom, EXTRA_PLAYER_BOTTOM)
        for phase in (1, 2, 3):
            self.game.reset(start_phase=phase)
            self.game.ready_timer = 0
            for key in (pygame.K_w, pygame.K_s, pygame.K_UP, pygame.K_DOWN):
                self.game.update(0.1, defaultdict(bool, {key: True}))
                self.assertEqual(self.game.player_y, PLAYER_Y)

    def test_shots_bombs_and_hit_detection_follow_vertical_position(self) -> None:
        self.game.player_y = 400
        self.game.fire()
        self.assertEqual(self.game.bullets[0].y, self.game.player_rect.top - 8)
        self.game.launch_bomb()
        self.assertEqual(self.game.bomb.y, self.game.player_rect.top - 10)
        self.game.bullets = [Bullet(*self.game.player_hitbox.center, 144, False)]
        self.game.update_bullets(0)
        self.assertEqual(self.game.lives, 4)
        self.assertFalse(self.game.bullets)

    def test_player_bullet_damages_boss_once_and_is_consumed(self) -> None:
        boss = self.game.extra_stage.boss
        self.game.bullets = [Bullet(*boss.rect.center, -510, True)]
        self.game.update_bullets(0)
        self.assertEqual(boss.hp, BOSS_MAX_HP - 1)
        self.assertFalse(self.game.bullets)
        self.game.update_bullets(0)
        self.assertEqual(boss.hp, BOSS_MAX_HP - 1)
        self.assertGreater(boss.hit_flash, 0)

    def test_bomb_hits_boss_once_and_can_launch_without_escorts(self) -> None:
        boss = self.game.extra_stage.boss
        self.game.aliens.clear()
        self.game.launch_bomb()
        self.assertIsNotNone(self.game.bomb)
        self.game.bomb = Bomb(boss.rect.centerx, boss.rect.bottom + 3)
        self.game.update_bomb(0)
        self.assertIsNone(self.game.bomb)
        self.assertEqual(boss.hp, BOSS_MAX_HP - BOSS_BOMB_DAMAGE)
        self.game.update_bomb(1)
        self.assertEqual(boss.hp, BOSS_MAX_HP - BOSS_BOMB_DAMAGE)

    def test_bomb_outside_boss_does_not_damage_it(self) -> None:
        self.game.explode_bomb((50, 450))
        self.assertEqual(self.game.extra_stage.boss.hp, BOSS_MAX_HP)

    def test_falling_escort_damages_boss_but_explosion_does_not(self) -> None:
        boss = self.game.extra_stage.boss
        alien = next(alien for alien in self.game.aliens if not alien.beam_cannon)
        alien.rect.center = boss.rect.center
        self.game.down_alien(alien)
        self.game.update_falling_aliens(0)
        self.assertEqual(boss.hp, BOSS_MAX_HP - BOSS_COLLISION_DAMAGE)
        self.assertFalse(self.game.falling_aliens)
        self.game.update_falling_aliens(0.1)
        self.assertEqual(boss.hp, BOSS_MAX_HP - BOSS_COLLISION_DAMAGE)

    def test_killing_all_escorts_does_not_clear_live_boss(self) -> None:
        self.game.aliens.clear()
        self.game.update(0, self.keys)
        self.assertEqual(self.game.wave_timer, 0)
        self.assertEqual(self.game.state, "playing")
        self.assertTrue(self.game.extra_stage.boss.alive)

    def test_boss_defeat_stops_attacks_scores_once_and_finishes_extra(self) -> None:
        self.begin_warning()
        self.game.bullets = [Bullet(200, 400, 180, False)]
        self.game.damage_boss(BOSS_MAX_HP)
        score = self.game.score
        self.assertGreaterEqual(score, 2000)
        self.assertFalse(self.game.aliens)
        self.assertFalse(self.game.extra_stage.cannons)
        self.assertFalse(self.game.bullets)
        self.assertTrue(self.game.explosions)
        self.game.damage_boss(10)
        self.assertEqual(self.game.score, score)
        for _ in range(180):
            self.game.update(1 / 60, self.keys)
        self.assertEqual(self.game.state, "victory")
        self.assertEqual(self.game.lives, 5)
        self.assertEqual(self.game.extra_stage.boss.hp, 0)

    def test_beam_warns_for_two_seconds_then_kills_even_with_invincibility(self) -> None:
        self.assertEqual(BEAM_WARNING_TIME, 2.0)
        for invincible in (0, 1):
            with self.subTest(invincible=invincible):
                self.game.reset(start_phase=4)
                self.game.ready_timer = 0
                cannon = self.begin_warning()
                self.game.invincible = invincible
                self.game.update_extra_stage(BEAM_WARNING_TIME - 0.001)
                self.assertEqual(self.game.lives, 5)
                self.assertEqual(cannon.state, "warning")
                self.game.update_extra_stage(0.001)
                self.assertEqual(cannon.state, "firing")
                self.assertEqual(self.game.lives, 5)  # 砲口からビームが伸びてくる。
                self.game.update_extra_stage(0.25)
                self.assertEqual(self.game.lives, 0)
                self.assertEqual(self.game.state, "game_over")

    def test_warning_and_firing_keep_initial_aim_and_shooter_position(self) -> None:
        cannon = self.begin_warning()
        origin = cannon.origin
        first_direction = cannon.direction
        expected = (pygame.Vector2(self.game.player_hitbox.center) - origin).normalize()
        self.assertLess((pygame.Vector2(first_direction) - expected).length(), 1e-9)
        alien = next(alien for alien in self.game.aliens if alien.beam_cannon)
        rect = alien.rect.copy()
        self.game.player_x = 50
        self.game.player_y = 350
        self.game.update_extra_stage(0.2)
        self.assertEqual(cannon.origin, origin)
        self.assertEqual(alien.rect, rect)
        self.assertEqual(cannon.direction, first_direction)
        self.game.player_x = 700
        self.game.update_extra_stage(BEAM_WARNING_TIME - 0.2)
        self.assertEqual(cannon.state, "firing")
        self.assertEqual(cannon.direction, first_direction)
        firing_direction = cannon.direction
        self.game.player_x = 50
        self.game.update_extra_stage(0.05)
        self.assertEqual(cannon.direction, firing_direction)
        self.assertEqual(alien.rect, rect)
        self.game.update_extra_stage(BEAM_FIRE_TIME)
        cannon.timer = 0
        self.game.update_extra_stage(0)
        self.assertEqual(cannon.state, "warning")
        expected = (pygame.Vector2(self.game.player_hitbox.center) - cannon.origin).normalize()
        self.assertLess((pygame.Vector2(cannon.direction) - expected).length(), 1e-9)
        self.assertNotEqual(cannon.direction, first_direction)

    def test_beam_uses_small_player_hitbox_and_has_safe_outside_edges(self) -> None:
        cannon = self.begin_warning()
        self.game.update_extra_stage(BEAM_WARNING_TIME)
        # 斜めのビームを発射後、機体の端だけが触れる位置へ避ける。
        self.game.player_x = 435
        self.game.update_extra_stage(0.25)
        self.assertEqual(self.game.lives, 5)
        self.assertTrue(cannon.hits(self.game.player_rect))
        self.assertFalse(cannon.hits(self.game.player_hitbox))
        self.game.player_x = 430
        self.game.update_extra_stage(0)
        self.assertEqual(self.game.state, "game_over")

    def test_killing_cannon_cancels_warning_or_active_beam(self) -> None:
        for active in (False, True):
            with self.subTest(active=active):
                self.game.reset(start_phase=4)
                cannon = self.begin_warning()
                alien = next(alien for alien in self.game.aliens if alien.beam_cannon)
                column = alien.column
                if active:
                    self.game.update_extra_stage(BEAM_WARNING_TIME)
                    self.assertEqual(cannon.state, "firing")
                self.game.down_alien(alien)
                self.assertNotIn(column, self.game.extra_stage.cannons)
                for _ in range(60):
                    self.game.update_extra_stage(1 / 60)
                self.assertEqual(self.game.lives, 5)

    def test_fired_beam_can_be_dodged_before_it_reaches_the_player(self) -> None:
        cannon = self.begin_warning()
        self.game.update_extra_stage(BEAM_WARNING_TIME)
        self.assertEqual(cannon.length, 0)
        direction = cannon.direction
        for _ in range(15):
            self.game.player_x -= 260 / 60
            self.game.update_extra_stage(1 / 60)
        self.assertEqual(self.game.lives, 5)
        self.assertEqual(cannon.direction, direction)

    def test_beam_geometry_uses_oriented_strip_and_finite_extension(self) -> None:
        cannon = BeamCannon(timer=BEAM_FIRE_TIME, state="firing", origin=(100, 100))
        cannon.direction = (math.sqrt(0.5), math.sqrt(0.5))
        target = pygame.Rect(297, 297, 6, 6)
        self.assertFalse(cannon.hits(target))
        cannon.timer -= 0.1
        self.assertAlmostEqual(cannon.length, BEAM_EXTENSION_SPEED * 0.1)
        self.assertFalse(cannon.hits(target))
        cannon.timer -= 0.1
        self.assertTrue(cannon.hits(target))
        # 外接矩形の内部でも、斜めのビームから離れた場所には当たらない。
        self.assertFalse(cannon.hits(pygame.Rect(300, 120, 6, 6)))
        self.assertFalse(cannon.hits(pygame.Rect(80, 80, 6, 6)))
        corners = [pygame.Vector2(point) for point in cannon.polygon()]
        self.assertAlmostEqual((corners[0] - corners[3]).length(), BEAM_WIDTH)

    def test_beam_stops_after_firing_duration_and_recharges(self) -> None:
        cannon = self.begin_warning()
        self.game.update_extra_stage(BEAM_WARNING_TIME)
        self.assertEqual(cannon.state, "firing")
        self.game.update_extra_stage(BEAM_FIRE_TIME)
        self.assertEqual(cannon.state, "cooldown")
        self.assertGreater(cannon.timer, 0)

    def test_pause_and_intro_freeze_beam_and_boss_timers(self) -> None:
        cannon = self.begin_warning()
        for paused, ready_timer in ((True, 0), (False, 1)):
            self.game.state = "paused" if paused else "playing"
            self.game.ready_timer = ready_timer
            before = (cannon.state, cannon.timer, self.game.extra_stage.elapsed, self.game.extra_stage.boss.shot_timer)
            self.game.update(0.2, self.keys)
            after = (cannon.state, cannon.timer, self.game.extra_stage.elapsed, self.game.extra_stage.boss.shot_timer)
            self.assertEqual(after, before)

    def test_boss_and_escorts_obey_total_cap_with_constant_boss_bullet_speed(self) -> None:
        self.game.extra_stage.boss.shot_timer = 0
        self.game.update_extra_stage(0)
        self.assertEqual(len(self.game.bullets), 32)
        self.assertTrue(all(bullet.boss_bullet for bullet in self.game.bullets))
        self.assertTrue(all(abs(math.hypot(bullet.velocity, bullet.horizontal_velocity) - 115.2) < 1e-9 for bullet in self.game.bullets))
        self.game.bullets.extend(Bullet(200, 400, 180, False) for _ in range(13))
        self.game.enemy_shot_timer = 0
        self.game.update_enemy_fire(0)
        self.assertEqual(sum(not bullet.boss_bullet for bullet in self.game.bullets), 14)
        self.game.bullets = [Bullet(200, 400, 180, False, boss_bullet=True) for _ in range(EXTRA_BULLET_LIMIT - 1)]
        self.game.extra_stage.boss.shot_timer = 0
        volley_index = self.game.extra_stage.boss.volley_index
        self.game.update_extra_stage(0)
        # 円の一部だけを撃たず、全弾分の空きができるまで待つ。
        self.assertEqual(len(self.game.bullets), EXTRA_BULLET_LIMIT - 1)
        self.assertEqual(self.game.extra_stage.boss.volley_index, volley_index)
        self.game.enemy_shot_timer = 0
        self.game.update_enemy_fire(0)
        self.assertEqual(len(self.game.bullets), EXTRA_BULLET_LIMIT)

    def test_dense_boss_patterns_cross_and_counter_rotate_at_constant_speed(self) -> None:
        boss = Boss()
        rosette = boss.barrage_shots(180)
        self.assertEqual(len(rosette), 32)
        self.assertEqual(len({shot.offset for shot in rosette}), 2)
        for group in (rosette[:16], rosette[16:]):
            angles = [math.atan2(shot.velocity[1], shot.velocity[0]) for shot in group]
            self.assertTrue(all(abs((after - before) % math.tau - math.tau / 16) < 1e-9 for before, after in zip(angles, angles[1:])))
        boss.volley_index = 1
        rotated = boss.barrage_shots(180)
        for index, sign in ((0, -1), (16, 1)):
            before = math.atan2(rosette[index].velocity[1], rosette[index].velocity[0])
            after = math.atan2(rotated[index].velocity[1], rotated[index].velocity[0])
            self.assertAlmostEqual(after - before, sign * 0.19)
        boss.volley_index = BARRAGE_VOLLEYS_PER_PATTERN
        self.assertEqual(boss.barrage_pattern, "CROSS")
        cross = boss.barrage_shots(180)
        self.assertEqual(len(cross), 34)
        self.assertTrue(all(shot.velocity[1] > 0 for shot in cross))
        self.assertGreater(cross[8].velocity[0], 0)  # 左砲口から右向き。
        self.assertLess(cross[25].velocity[0], 0)  # 右砲口から左向き。
        boss.volley_index = 2 * BARRAGE_VOLLEYS_PER_PATTERN
        self.assertEqual(boss.barrage_pattern, "HELIX")
        helix = boss.barrage_shots(180)
        self.assertEqual(len(helix), 16)
        boss.volley_index += 1
        rotated = boss.barrage_shots(180)
        for index, sign in ((0, -1), (8, 1)):
            before = math.atan2(helix[index].velocity[1], helix[index].velocity[0])
            after = math.atan2(rotated[index].velocity[1], rotated[index].velocity[0])
            self.assertAlmostEqual(after - before, sign * 0.28)
        self.assertTrue(all(abs(math.hypot(*shot.velocity) - 180) < 1e-9 for shot in [*rosette, *cross, *helix]))
        boss.volley_index = 3 * BARRAGE_VOLLEYS_PER_PATTERN
        self.assertEqual(boss.barrage_pattern, "ROSETTE")

    def test_barrage_density_and_screen_cap_during_sustained_fire(self) -> None:
        self.game.aliens.clear()  # ボス単体の弾幕を、砲台の即死ビームなしで計測する。
        self.game.invincible = 100
        peak_count = 0
        patterns = set()
        for _ in range(20 * 60):
            self.game.update_extra_stage(1 / 60)
            self.game.update_bullets(1 / 60)
            count = sum(not bullet.friendly for bullet in self.game.bullets)
            self.assertLessEqual(count, EXTRA_BULLET_LIMIT)
            peak_count = max(peak_count, count)
            patterns.add(self.game.extra_stage.boss.last_barrage_pattern)
        self.assertGreater(peak_count, 100)
        self.assertEqual(patterns, {"ROSETTE", "CROSS", "HELIX"})

    def test_boss_bullets_move_in_emitted_directions_and_bomb_erases_them(self) -> None:
        self.game.extra_stage.boss.shot_timer = 0
        self.game.update_extra_stage(0)
        bullets = self.game.bullets[:]
        starts = [(bullet.x, bullet.y) for bullet in bullets]
        for bullet, (x, y) in zip(bullets, starts):
            bullet.advance(0.25)
            self.assertAlmostEqual(bullet.x - x, bullet.horizontal_velocity * 0.25)
            self.assertAlmostEqual(bullet.y - y, bullet.velocity * 0.25)
            self.assertEqual(bullet.rect.size, (8, 8))
        self.game.explode_bomb((400, 212))
        self.assertFalse(self.game.bullets)

    def test_warning_and_firing_have_sound_events_and_render_in_all_states(self) -> None:
        sounds = Mock(spec=SoundEffects)
        self.game.sounds = sounds
        cannon = self.begin_warning()
        sounds.play.assert_any_call("beam_charge")
        self.game.draw()
        self.game.update_extra_stage(BEAM_WARNING_TIME)
        sounds.play.assert_any_call("beam_fire")
        self.assertEqual(cannon.state, "firing")
        for state in ("title", "playing", "paused", "game_over", "victory"):
            self.game.state = state
            self.game.draw()

    def test_warning_stays_visible_on_red_background_and_does_not_hide_bullets(self) -> None:
        self.game.draw()
        baseline = self.screen.copy()
        cannon = self.begin_warning()
        direction = pygame.Vector2(cannon.direction)
        points = [pygame.Vector2(cannon.origin) + direction * distance for distance in (200, 320)]
        points = [(round(point.x), round(point.y)) for point in points]
        for elapsed in (0, 0.9, 1.099):
            self.game.update_extra_stage(elapsed)
            self.assertEqual(cannon.state, "warning")
            self.game.draw()
            for point in points:
                before = baseline.get_at(point)
                after = self.screen.get_at(point)
                contrast = sum(abs(after[channel] - before[channel]) for channel in range(3))
                self.assertGreaterEqual(contrast, 90)
        # 予告帯が弾を上から赤く塗りつぶさない。
        bullet = Bullet(*points[0], -510, True)
        self.game.bullets = [bullet]
        self.game.draw()
        self.assertEqual(tuple(self.screen.get_at(points[0]))[:3], (225, 235, 240))


if __name__ == "__main__":
    unittest.main()
