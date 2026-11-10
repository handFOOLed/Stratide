import unittest

from retry import may_retry


class RetryTests(unittest.TestCase):
    def test_not_started_can_retry(self):
        self.assertTrue(may_retry("not_started"))

    def test_unknown_must_not_retry(self):
        self.assertFalse(may_retry("unknown"))


if __name__ == "__main__":
    unittest.main()
