"""Independent exhaustive oracles for second-order text-composite fusion."""

import itertools
import unittest

import numpy as np

from cga_text_new_search import solve_chain


def chain_cost(factors, labels):
    return sum(float(factors[x, labels[x - 1] if x else 0, label,
                             labels[x + 1] if x + 1 < len(labels) else 0])
               for x, label in enumerate(labels))


class ExactFusionTests(unittest.TestCase):
    def test_matches_full_enumeration_including_short_chains(self):
        rng = np.random.default_rng(714)
        for width in (1, 2, 3, 5, 7):
            for k in (1, 2, 3):
                for trial in range(3):
                    with self.subTest(width=width, k=k, trial=trial):
                        factors = rng.integers(-50, 80, (width, k, k, k)).astype(np.float64)
                        expected = min(chain_cost(factors, labels)
                                       for labels in itertools.product(range(k), repeat=width))
                        labels, score = solve_chain(factors)
                        self.assertEqual(score, expected)
                        self.assertEqual(chain_cost(factors, labels), expected)

    def test_collective_move_escapes_single_cell_minimum(self):
        # The incumbent 000 cannot improve by changing any single label.
        # Only the genuinely triple-dependent move to 111 reaches zero.
        factors = np.zeros((3, 2, 2, 2))
        factors[1] = 30
        factors[1, 0, 0, 0] = 10
        factors[1, 1, 1, 1] = 0
        for x in range(3):
            labels = [0, 0, 0]
            labels[x] = 1
            self.assertGreater(chain_cost(factors, labels), 10)
        labels, score = solve_chain(factors)
        np.testing.assert_array_equal(labels, [1, 1, 1])
        self.assertEqual(score, 0)

    def test_ties_keep_the_complete_incumbent(self):
        for width in (1, 2, 8):
            factors = np.zeros((width, 4, 4, 4))
            labels, score = solve_chain(factors)
            np.testing.assert_array_equal(labels, np.zeros(width, dtype=np.int32))
            self.assertEqual(score, 0)

    def test_edges_fix_absent_neighbor_to_zero(self):
        factors = np.zeros((2, 3, 3, 3))
        factors[0, 1:, :, :] = -100000
        factors[1, :, :, 1:] = -100000
        factors[0, 0, 2, 1] = -7
        labels, score = solve_chain(factors)
        np.testing.assert_array_equal(labels, [2, 1])
        self.assertEqual(score, -7)

    def test_float_scores_and_repeated_calls_are_deterministic(self):
        factors = np.random.default_rng(511).random((6, 3, 3, 3)) * 10000
        expected = min(chain_cost(factors, labels)
                       for labels in itertools.product(range(3), repeat=6))
        a, score = solve_chain(factors)
        b, second_score = solve_chain(factors)
        self.assertAlmostEqual(score, expected, places=9)
        self.assertAlmostEqual(chain_cost(factors, a), expected, places=9)
        np.testing.assert_array_equal(a, b)
        self.assertEqual(score, second_score)

    def test_infinite_costs_can_exclude_assignments(self):
        factors = np.full((3, 2, 2, 2), np.inf)
        factors[0, 0, 1, 1] = 2
        factors[1, 1, 1, 1] = 3
        factors[2, 1, 1, 0] = 4
        labels, score = solve_chain(factors)
        np.testing.assert_array_equal(labels, [1, 1, 1])
        self.assertEqual(score, 9)

    def test_rejects_malformed_or_unsatisfiable_input(self):
        for factors in (np.zeros((0, 2, 2, 2)), np.zeros((1, 2, 2)),
                        np.zeros((1, 2, 3, 2)), np.full((2, 2, 2, 2), np.nan),
                        np.full((2, 2, 2, 2), -np.inf),
                        np.full((2, 2, 2, 2), np.inf)):
            with self.subTest(shape=factors.shape):
                with self.assertRaises(ValueError):
                    solve_chain(factors)


if __name__ == "__main__":
    unittest.main()
