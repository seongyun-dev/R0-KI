import unittest

from aiot_robot.patrol_activation import PatrolActivation


class PatrolActivationTest(unittest.TestCase):
    def test_disabled_by_default_and_resumes_only_after_enable(self):
        activation = PatrolActivation()

        self.assertFalse(activation.enabled)
        self.assertFalse(activation.wait(0.001))

        activation.enable()
        self.assertTrue(activation.enabled)
        self.assertTrue(activation.wait(0.001))

        activation.disable()
        self.assertFalse(activation.enabled)
        self.assertFalse(activation.wait(0.001))


if __name__ == "__main__":
    unittest.main()
