import unittest
import torch
import maskedtensor
from maskedtensor import masked_tensor
from torch.testing._internal.common_utils import TestCase


class TestFusedLayer(TestCase):
    def test_add(self):
        data = torch.arange(5.0)
        mask = torch.tensor([True, True, False, True, False])
        m0 = maskedtensor.masked_tensor(data, mask)
        m1 = maskedtensor.masked_tensor(data, ~mask)
        self.assertRaises(ValueError, lambda: m0 + m1)

if __name__ == "__main__":
    unittest.main()