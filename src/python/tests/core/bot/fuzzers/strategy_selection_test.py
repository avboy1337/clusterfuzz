# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for strategy selection file."""

import unittest

from google.cloud import ndb

from bot.fuzzers import strategy_selection
from bot.tasks import fuzz_task
from datastore import data_types
from fuzzing import strategy
from system import environment
from tests.test_libs import helpers as test_helpers
from tests.test_libs import test_utils


class TestDefaultStrategySelectionLibFuzzerPatched(unittest.TestCase):
  """Tests whether program properly generates strategy pools for use by the
  libFuzzer launcher."""

  def setUp(self):
    """Set up method for strategy pool generator tests with patch."""
    test_helpers.patch_environ(self)
    test_helpers.patch(self,
                       ['bot.fuzzers.engine_common.decide_with_probability'])
    self.mock.decide_with_probability.return_value = True

  def test_default_pool_deterministic(self):
    """Deterministically tests the default strategy pool generator."""
    strategy_pool = strategy_selection.generate_default_strategy_pool(
        strategy_list=strategy.LIBFUZZER_STRATEGY_LIST, use_generator=True)

    # Ml rnn and radamsa strategies are mutually exclusive. Because of how we
    # patch, ml rnn will evaluate to false, however this depends on the
    # implementation.
    self.assertTrue(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_RADAMSA_STRATEGY))
    self.assertFalse(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_ML_RNN_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.CORPUS_SUBSET_STRATEGY))
    self.assertTrue(
        strategy_pool.do_strategy(strategy.RANDOM_MAX_LENGTH_STRATEGY))
    self.assertTrue(
        strategy_pool.do_strategy(strategy.RECOMMENDED_DICTIONARY_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.VALUE_PROFILE_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.FORK_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.MUTATOR_PLUGIN_STRATEGY))


class TestStrategySelectionLibFuzzerPatchless(unittest.TestCase):
  """Tests to see whether a default strategy pool is properly generated by the
  file for the libFuzzer launcher."""

  def test_default_pool_generator(self):
    """Ensures that a call to generate_default_strategy_pool does not yield an
    exception. Deterministic behaviors are tested in the previous test."""
    strategy_selection.generate_default_strategy_pool(
        strategy_list=strategy.LIBFUZZER_STRATEGY_LIST, use_generator=True)


@test_utils.with_cloud_emulators('datastore')
class TestMultiArmedBanditStrategySelectionLibFuzzerPatch(unittest.TestCase):
  """Tests whether a multi armed bandit strategy pool is properly
  generated according to the specified distribution for the libFuzzer
  launcher."""

  def setUp(self):
    """Put data in the local ndb table the tests to query from and set
    bandit selection environment variable."""
    test_helpers.patch_environ(self)

    data = []

    strategy1 = data_types.FuzzStrategyProbability()
    strategy1.strategy_name = 'fork,corpus_subset,recommended_dict,'
    strategy1.probability = 0.33
    strategy1.engine = 'libFuzzer'
    data.append(strategy1)

    strategy2 = data_types.FuzzStrategyProbability()
    strategy2.strategy_name = ('random_max_len,corpus_mutations_ml_rnn,'
                               'value_profile,recommended_dict,')
    strategy2.probability = 0.34
    strategy2.engine = 'libFuzzer'
    data.append(strategy2)

    strategy3 = data_types.FuzzStrategyProbability()
    strategy3.strategy_name = ('corpus_mutations_radamsa,'
                               'random_max_len,corpus_subset,')
    strategy3.probability = 0.33
    strategy3.engine = 'libFuzzer'
    data.append(strategy3)
    ndb.put_multi(data)

    distribution = fuzz_task.get_strategy_distribution_from_ndb()

    environment.set_value('USE_BANDIT_STRATEGY_SELECTION', True)
    environment.set_value('STRATEGY_SELECTION_DISTRIBUTION', distribution)

  def test_multi_armed_bandit_strategy_pool(self):
    """Ensures a call to the multi armed bandit strategy selection function
    doesn't yield an exception through any of the experimental paths."""
    environment.set_value('STRATEGY_SELECTION_METHOD', 'default')
    strategy_selection.generate_weighted_strategy_pool(
        strategy_list=strategy.LIBFUZZER_STRATEGY_LIST,
        use_generator=True,
        engine_name='libFuzzer')
    environment.set_value('STRATEGY_SELECTION_METHOD', 'multi_armed_bandit')
    strategy_selection.generate_weighted_strategy_pool(
        strategy_list=strategy.LIBFUZZER_STRATEGY_LIST,
        use_generator=True,
        engine_name='libFuzzer')


@test_utils.with_cloud_emulators('datastore')
class TestMultiArmedBanditStrategySelectionLibFuzzer(unittest.TestCase):
  """Tests whether multi armed bandit strategy pool is properly generated
  according to the specified distribution for the libFuzzer launcher.

  Deterministic tests. Only one strategy is put in the ndb table upon setup,
  so we know what the drawn strategy pool should be."""

  def setUp(self):
    """Put data in the local ndb table the tests to query from."""
    test_helpers.patch_environ(self)
    test_helpers.patch(self,
                       ['bot.fuzzers.engine_common.decide_with_probability'])
    self.mock.decide_with_probability.return_value = True

    data = []

    strategy1 = data_types.FuzzStrategyProbability()
    strategy1.strategy_name = ('random_max_len,corpus_mutations_ml_rnn,'
                               'value_profile,recommended_dict,')
    strategy1.probability = 1
    strategy1.engine = 'libFuzzer'
    data.append(strategy1)
    ndb.put_multi(data)

    distribution = fuzz_task.get_strategy_distribution_from_ndb()

    environment.set_value('USE_BANDIT_STRATEGY_SELECTION', True)
    environment.set_value('STRATEGY_SELECTION_DISTRIBUTION', distribution)

  def test_weighted_strategy_pool(self):
    """Tests whether a proper strategy pool is returned by the multi armed
    bandit selection implementation with medium temperature.

    Based on deterministic strategy selection. Mutator plugin is patched to
    be included in our strategy pool."""
    environment.set_value('STRATEGY_SELECTION_METHOD', 'multi_armed_bandit')
    strategy_pool = strategy_selection.generate_weighted_strategy_pool(
        strategy_list=strategy.LIBFUZZER_STRATEGY_LIST,
        use_generator=True,
        engine_name='libFuzzer')
    self.assertTrue(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_ML_RNN_STRATEGY))
    self.assertTrue(
        strategy_pool.do_strategy(strategy.RANDOM_MAX_LENGTH_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.VALUE_PROFILE_STRATEGY))
    self.assertTrue(
        strategy_pool.do_strategy(strategy.RECOMMENDED_DICTIONARY_STRATEGY))
    self.assertFalse(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_RADAMSA_STRATEGY))
    self.assertFalse(strategy_pool.do_strategy(strategy.FORK_STRATEGY))


class TestDefaultStrategySelectionAFLPatched(unittest.TestCase):
  """Tests whether program properly generates strategy pools for use by the
  AFL launcher."""

  def setUp(self):
    """Set up method for strategy pool generator tests with patch."""
    test_helpers.patch_environ(self)
    test_helpers.patch(self,
                       ['bot.fuzzers.engine_common.decide_with_probability'])
    self.mock.decide_with_probability.return_value = True

  def test_default_pool_deterministic(self):
    """Deterministically tests the default strategy pool generator."""
    strategy_pool = strategy_selection.generate_default_strategy_pool(
        strategy_list=strategy.AFL_STRATEGY_LIST, use_generator=True)

    # Ml rnn and radamsa strategies are mutually exclusive. Because of how we
    # patch, ml rnn will evaluate to false, however this depends on the
    # implementation.
    self.assertTrue(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_RADAMSA_STRATEGY))
    self.assertFalse(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_ML_RNN_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.CORPUS_SUBSET_STRATEGY))


class TestStrategySelectionAFLPatchless(unittest.TestCase):
  """Tests to see whether a default strategy pool is properly generated by the
  file for the AFL launcher."""

  def test_default_pool_generator(self):
    """Ensures that a call to generate_default_strategy_pool does not yield an
    exception. Deterministic behaviors are tested in the previous test."""
    strategy_selection.generate_default_strategy_pool(
        strategy_list=strategy.AFL_STRATEGY_LIST, use_generator=True)


@test_utils.with_cloud_emulators('datastore')
class TestMultiArmedBanditStrategySelectionAFLPatch(unittest.TestCase):
  """Tests whether a multi armed bandit strategy pool is properly
  generated according to the specified distribution for the AFL launcher."""

  def setUp(self):
    """Put data in the local ndb table the tests to query from and set
    bandit selection environment variable."""
    test_helpers.patch_environ(self)

    data = []

    strategy1 = data_types.FuzzStrategyProbability()
    strategy1.strategy_name = 'corpus_mutations_ml_rnn,corpus_subset,'
    strategy1.probability = 0.33
    strategy1.engine = 'afl'
    data.append(strategy1)

    strategy2 = data_types.FuzzStrategyProbability()
    strategy2.strategy_name = ('corpus_mutations_radamsa,corpus_subset,')
    strategy2.probability = 0.34
    strategy2.engine = 'afl'
    data.append(strategy2)

    strategy3 = data_types.FuzzStrategyProbability()
    strategy3.strategy_name = ('corpus_subset,')
    strategy3.probability = 0.33
    strategy3.engine = 'afl'
    data.append(strategy3)
    ndb.put_multi(data)

    distribution = fuzz_task.get_strategy_distribution_from_ndb()

    environment.set_value('USE_BANDIT_STRATEGY_SELECTION', True)
    environment.set_value('STRATEGY_SELECTION_DISTRIBUTION', distribution)

  def test_multi_armed_bandit_strategy_pool(self):
    """Ensures a call to the multi armed bandit strategy selection function
    doesn't yield an exception through any of the experimental paths."""
    environment.set_value('STRATEGY_SELECTION_METHOD', 'default')
    strategy_selection.generate_weighted_strategy_pool(
        strategy_list=strategy.AFL_STRATEGY_LIST,
        use_generator=True,
        engine_name='afl')
    environment.set_value('STRATEGY_SELECTION_METHOD', 'multi_armed_bandit')
    strategy_selection.generate_weighted_strategy_pool(
        strategy_list=strategy.AFL_STRATEGY_LIST,
        use_generator=True,
        engine_name='afl')


@test_utils.with_cloud_emulators('datastore')
class TestMultiArmedBanditStrategySelectionAFL(unittest.TestCase):
  """Tests whether multi armed bandit strategy pool is properly generated
  according to the specified distribution for the AFL launcher.

  Deterministic tests. Only one strategy is put in the ndb table upon setup,
  so we know what the drawn strategy pool should be."""

  def setUp(self):
    """Put data in the local ndb table the tests to query from."""
    test_helpers.patch_environ(self)
    test_helpers.patch(self,
                       ['bot.fuzzers.engine_common.decide_with_probability'])
    self.mock.decide_with_probability.return_value = True

    data = []

    strategy1 = data_types.FuzzStrategyProbability()
    strategy1.strategy_name = 'corpus_mutations_ml_rnn,corpus_subset,'
    strategy1.probability = 1
    strategy1.engine = 'afl'
    data.append(strategy1)
    ndb.put_multi(data)

    distribution = fuzz_task.get_strategy_distribution_from_ndb()

    environment.set_value('USE_BANDIT_STRATEGY_SELECTION', True)
    environment.set_value('STRATEGY_SELECTION_DISTRIBUTION', distribution)

  def test_weighted_strategy_pool(self):
    """Tests whether a proper strategy pool is returned by the multi armed
    bandit selection implementation with medium temperature.

    Based on deterministic strategy selection. Mutator plugin is patched to
    be included in our strategy pool."""
    environment.set_value('STRATEGY_SELECTION_METHOD', 'multi_armed_bandit')
    strategy_pool = strategy_selection.generate_weighted_strategy_pool(
        strategy_list=strategy.AFL_STRATEGY_LIST,
        use_generator=True,
        engine_name='afl')
    self.assertTrue(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_ML_RNN_STRATEGY))
    self.assertFalse(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_RADAMSA_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.CORPUS_SUBSET_STRATEGY))
