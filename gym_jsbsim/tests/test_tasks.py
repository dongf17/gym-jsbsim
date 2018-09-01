import unittest
import math
import numpy as np
import gym_jsbsim.properties as prp
from gym_jsbsim import rewards, utils
from gym_jsbsim.assessors import Assessor
from gym_jsbsim.aircraft import Aircraft, cessna172P
from gym_jsbsim.tasks import HeadingControlTask, TurnHeadingControlTask
from gym_jsbsim.tests.stubs import SimStub, TransitioningSimStub


class TestHeadingControlTask(unittest.TestCase):
    default_shaping = HeadingControlTask.Shaping.OFF
    default_episode_time_s = 15.0
    default_step_frequency_hz = 5
    default_aircraft = cessna172P

    def setUp(self):
        self.task = self.make_task()
        sim = SimStub.make_valid_state_stub(self.task)
        _ = self.task.observe_first_state(sim)  # causes task to init new-episode attributes

        self.dummy_action = np.asarray([0 for _ in range(len(self.task.action_variables))])

    def get_class_under_test(self):
        return HeadingControlTask

    def make_task(self,
                  shaping_type: HeadingControlTask.Shaping = default_shaping,
                  episode_time_s: float = default_episode_time_s,
                  step_frequency_hz: float = default_step_frequency_hz,
                  aircraft: Aircraft = default_aircraft) -> HeadingControlTask:
        task_class = self.get_class_under_test()
        return task_class(shaping_type=shaping_type,
                          episode_time_s=episode_time_s,
                          step_frequency_hz=step_frequency_hz,
                          aircraft=aircraft)

    def get_sim_with_sate(self,
                          task=None,
                          time_s = 0.0,
                          dist_travel_m = 0.0,
                          heading_deg = 0.0,
                          altitude_ft = None,
                          roll_rad = 0.0) -> SimStub:
        if task is None:
            task = self.task
        sim = SimStub.make_valid_state_stub(task)

        sim[prp.sim_time_s] = time_s
        sim[prp.dist_travel_m] = dist_travel_m
        sim[prp.heading_deg] = heading_deg
        sim[prp.altitude_sl_ft] = altitude_ft if altitude_ft is not None else task.INITIAL_ALTITUDE_FT
        sim[prp.roll_rad] = roll_rad
        return sim

    def get_initial_state_sim(self, task=None) -> SimStub:
        if task is None:
            task = self.task
        sim = SimStub.make_valid_state_stub(task)

        # set properties to reasonable initial episode values
        sim[prp.sim_time_s] = 0.0
        sim[prp.dist_travel_m] = 0.0
        sim[prp.heading_deg] = task.INITIAL_HEADING_DEG
        sim[prp.altitude_sl_ft] = task.get_initial_conditions()[prp.initial_altitude_ft]
        sim[prp.roll_rad] = 0
        return sim

    def get_perfect_state_sim(self, task=None, terminal=True) -> SimStub:
        if task is None:
            task = self.task
        sim = SimStub.make_valid_state_stub(task)
        task.observe_first_state(sim)
        target_heading = self.get_target_heading(sim)

        # set properties to reasonable initial episode values
        if terminal:
            time = task.max_time_s + 1
        else:
            time = task.max_time_s - 1
        sim[prp.sim_time_s] = time
        sim[prp.dist_travel_m] = task.distance_parallel_m.max
        sim[prp.heading_deg] = target_heading
        sim[prp.altitude_sl_ft] = task.get_initial_conditions()[prp.initial_altitude_ft]
        sim[prp.roll_rad] = 0

        # move position along target heading
        sim[prp.lng_geoc_deg] += math.sin(math.radians(target_heading))
        sim[prp.lat_geod_deg] += math.cos(math.radians(target_heading))
        return sim

    def get_target_heading(self, sim: SimStub):
        return self.task.INITIAL_HEADING_DEG

    def test_init_shaping_off(self):
        task = self.make_task(shaping_type=HeadingControlTask.Shaping.OFF)

        self.assertIsInstance(task.assessor, Assessor)
        self.assertEqual(2, len(task.assessor.base_components))
        self.assertFalse(task.assessor.shaping_components)  # assert empty

    def test_init_shaping_basic(self):
        task = self.make_task(shaping_type=HeadingControlTask.Shaping.BASIC)

        self.assertIsInstance(task.assessor, Assessor)
        self.assertEqual(2, len(task.assessor.base_components))
        self.assertEqual(2, len(task.assessor.shaping_components))

    def test_init_shaping_additive(self):
        task = self.make_task(shaping_type=HeadingControlTask.Shaping.ADDITIVE)

        self.assertIsInstance(task.assessor, Assessor)
        self.assertEqual(2, len(task.assessor.base_components))
        self.assertEqual(4, len(task.assessor.shaping_components))

    def test_get_intial_conditions_valid_target_heading(self):
        self.setUp()

        ics = self.task.get_initial_conditions()
        initial_heading = ics[prp.initial_heading_deg]

        self.assertLessEqual(prp.heading_deg.min, initial_heading)
        self.assertGreaterEqual(prp.heading_deg.max, initial_heading)

    def test_get_initial_conditions_contains_all_props(self):
        ics = self.task.get_initial_conditions()

        self.assertIsInstance(ics, dict)
        for prop, value in self.task.base_initial_conditions.items():
            self.assertAlmostEqual(value, ics[prop])

        steady_level_task_ic_properties = [prp.initial_u_fps,
                                           prp.initial_v_fps,
                                           prp.initial_w_fps,
                                           prp.initial_p_radps,
                                           prp.initial_q_radps,
                                           prp.initial_r_radps,
                                           prp.initial_heading_deg
                                           ]
        for prop in steady_level_task_ic_properties:
            self.assertIn(prop, ics.keys(),
                          msg='expected HeadingControlTask to set value for'
                              f'property {prop} but not found in ICs')

    def test_observe_first_state_returns_valid_state(self):
        sim = SimStub.make_valid_state_stub(self.task)

        first_state = self.task.observe_first_state(sim)

        self.assertEqual(len(first_state), len(self.task.state_variables))
        self.assertIsInstance(first_state, tuple)

    def test_task_first_observation_inputs_controls(self):
        dummy_sim = SimStub.make_valid_state_stub(self.task)
        _ = self.task.observe_first_state(dummy_sim)

        # check engine as expected
        self.assertAlmostEqual(self.task.THROTTLE_CMD, dummy_sim[prp.throttle_cmd])
        self.assertAlmostEqual(self.task.MIXTURE_CMD, dummy_sim[prp.mixture_cmd])
        self.assertAlmostEqual(1.0, dummy_sim[prp.engine_running])

    def test_task_step_correct_return_types(self):
        sim = SimStub.make_valid_state_stub(self.task)
        steps = 1
        _ = self.task.observe_first_state(sim)

        state, reward, is_terminal, info = self.task.task_step(sim, self.dummy_action, steps)

        self.assertIsInstance(state, tuple)
        self.assertEqual(len(state), len(self.task.state_variables))

        self.assertIsInstance(reward, float)
        self.assertIsInstance(is_terminal, bool)
        self.assertIsInstance(info, dict)

    def test_task_step_returns_reward_in_info(self):
        sim = SimStub.make_valid_state_stub(self.task)
        steps = 1
        _ = self.task.observe_first_state(sim)

        _, reward_scalar, _, info = self.task.task_step(sim, self.dummy_action, steps)
        reward_object = info['reward']

        self.assertIsInstance(reward_object, rewards.Reward)
        self.assertAlmostEqual(reward_object.reward(), reward_scalar)

    def test_task_step_returns_non_terminal_time_less_than_max(self):
        sim = SimStub.make_valid_state_stub(self.task)
        _ = self.task.observe_first_state(sim)
        non_terminal_time = self.default_episode_time_s - 1
        sim[prp.sim_time_s] = non_terminal_time
        steps = 1

        _, _, is_terminal, _ = self.task.task_step(sim, self.dummy_action, steps)

        self.assertFalse(is_terminal)

    def test_task_step_returns_terminal_time_exceeds_max(self):
        sim = SimStub.make_valid_state_stub(self.task)
        _ = self.task.observe_first_state(sim)
        terminal_time = self.default_episode_time_s + 1
        sim[prp.sim_time_s] = terminal_time
        steps = 1

        _, _, is_terminal, _ = self.task.task_step(sim, self.dummy_action, steps)

        self.assertTrue(is_terminal)

    def test_task_step_returns_terminal_time_equals_max(self):
        sim = SimStub.make_valid_state_stub(self.task)
        _ = self.task.observe_first_state(sim)
        terminal_time = self.default_episode_time_s
        sim[prp.sim_time_s] = terminal_time
        steps = 1

        _, _, is_terminal, _ = self.task.task_step(sim, self.dummy_action, steps)

        self.assertTrue(is_terminal)

    def test_task_step_correct_terminal_reward_optimal_behaviour_no_shaping(self):
        self.setUp()
        task = self.make_task(shaping_type=HeadingControlTask.Shaping.OFF,
                              episode_time_s=1.,
                              step_frequency_hz=1.)
        initial_state_sim = self.get_initial_state_sim(task)
        _ = task.observe_first_state(initial_state_sim)
        final_state_sim = self.get_perfect_state_sim(task, terminal=True)
        sim = TransitioningSimStub(initial_state_sim, final_state_sim)

        state, reward, done, info = task.task_step(sim, self.dummy_action, 1)

        # aircraft moved maximum distance on correct heading and maintained
        # altitude, so we expect reward of 1.0
        self.assertAlmostEqual(1., reward)

    def test_task_step_correct_non_terminal_reward_optimal_behaviour_no_shaping(self):
        self.setUp()
        task = self.make_task(shaping_type=HeadingControlTask.Shaping.OFF,
                              episode_time_s=1.,
                              step_frequency_hz=1.)
        initial_state_sim = self.get_initial_state_sim(task)
        _ = task.observe_first_state(initial_state_sim)
        final_state_sim = self.get_perfect_state_sim(task, terminal=False)
        sim = TransitioningSimStub(initial_state_sim, final_state_sim)

        state, reward, done, info = task.task_step(sim, self.dummy_action, 1)

        # aircraft maintained correct altitude (1.0) but sim is non-terminal
        # so we expect no distance traveled reward (0.0) average to 0.5
        self.assertAlmostEqual(0.5, reward)

    def test_task_step_correct_terminal_reward_optimal_behaviour_shaping(self):
        self.setUp()
        Shaping = HeadingControlTask.Shaping
        for shaping in (Shaping.OFF, Shaping.BASIC, Shaping.ADDITIVE, Shaping.SEQUENTIAL_CONT):
            task = self.make_task(shaping_type=shaping,
                                  episode_time_s=1.,
                                  step_frequency_hz=1.)
            initial_state_sim = self.get_initial_state_sim(task)
            _ = task.observe_first_state(initial_state_sim)
            final_state_sim = self.get_perfect_state_sim(task, terminal=True)
            sim = TransitioningSimStub(initial_state_sim, final_state_sim)

            _, _, _, info = task.task_step(sim, self.dummy_action, 1)
            reward_obj: rewards.Reward = info['reward']

            # aircraft moved maximum distance on correct heading and maintained
            # altitude, so we expect non-shaping reward of 1.0
            self.assertAlmostEqual(1., reward_obj.non_shaping_reward())

    def test_task_step_correct_sequential_reward_shaping_(self):
        self.setUp()
        task = self.make_task(shaping_type=HeadingControlTask.Shaping.SEQUENTIAL_CONT),

    def test_observe_first_state_correct_heading_error(self):
        self.setUp()
        sim = SimStub.make_valid_state_stub(self.task)
        _ = self.task.observe_first_state(sim)

        heading = sim[prp.heading_deg]
        target_heading = sim[self.task.target_heading_deg]
        error_deg = heading - target_heading
        expected_acute_error_deg = utils.reduce_reflex_angle_deg(error_deg)
        actual_error_deg = sim[self.task.heading_error_deg]

        self.assertAlmostEqual(expected_acute_error_deg, actual_error_deg)

    def test_task_step_state_correct_heading_error(self):
        self.setUp()
        sim = SimStub.make_valid_state_stub(self.task)
        state = self.task.observe_first_state(sim)

        heading = sim[prp.heading_deg]
        target_heading = sim[self.task.target_heading_deg]
        error_deg = heading - target_heading
        expected_acute_error_deg = utils.reduce_reflex_angle_deg(error_deg)

        sim_error_deg = sim[self.task.heading_error_deg]
        heading_error_state_index = self.task.state_variables.index(self.task.heading_error_deg)
        state_error_deg = state[heading_error_state_index]

        self.assertAlmostEqual(expected_acute_error_deg, sim_error_deg)
        self.assertAlmostEqual(expected_acute_error_deg, state_error_deg)


class TestTurnHeadingControlTask(TestHeadingControlTask):

    def setUp(self):
        super().setUp()
        assert isinstance(self.task, TurnHeadingControlTask)

    def get_class_under_test(self):
        return TurnHeadingControlTask

    def get_target_heading(self, sim: SimStub):
        return sim[TurnHeadingControlTask.target_heading_deg]

    def test_observe_first_state_creates_desired_heading_in_expected_range(self):
        sim = SimStub.make_valid_state_stub(self.task)
        _ = self.task.observe_first_state(sim)

        desired_heading = sim[HeadingControlTask.target_heading_deg]
        self.assertGreaterEqual(desired_heading, 0)
        self.assertLessEqual(desired_heading, 360)

    def test_observe_first_state_changes_desired_heading(self):
        sim = SimStub.make_valid_state_stub(self.task)
        _ = self.task.observe_first_state(sim)
        desired_heading = sim[HeadingControlTask.target_heading_deg]

        _ = self.task.observe_first_state(sim)
        new_desired_heading = sim[HeadingControlTask.target_heading_deg]

        self.assertNotEqual(desired_heading, new_desired_heading)
