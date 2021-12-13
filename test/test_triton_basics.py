# Copyright (c) Facebook, Inc. and its affiliates. All rights reserved.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.


import torch

_triton_available = torch.cuda.is_available()
if _triton_available:
    try:
        import triton
        import triton.language as tl

    except (ImportError, ModuleNotFoundError):
        _triton_available = False

if _triton_available:

    @triton.jit
    def k_mean(X, Mean, Var, stride, N, **META):
        # fmt: on
        """
        Fused layernorm kernel over a 3d tensor.
        The layer norm is applied over the last dimension.

        Compute
            y = (x - E(x))/(sqrt(var(x) + epsilon)) * gamma + beta
        """

        row = tl.program_id(0)
        cols = tl.arange(0, META["BLOCK_SIZE_N"])

        # Move to this row
        x_ptrs = X + row * stride + cols
        x = tl.load(x_ptrs, mask=cols < N, other=0.0).to(tl.float32)
        x = tl.where(cols < N, x, 0.0)

        # Compute variance
        x_mean = tl.sum(x, axis=0) / N
        x_zm = x - x_mean
        x_zm = tl.where(cols < N, x_zm, 0.0)  # THIS SHOULD NOT BE NEEDED
        x_var = tl.sum(x_zm * x_zm, axis=0) / N
        tl.store(Mean + row, x_mean)
        tl.store(Var + row, x_var)

    def stats(x: torch.Tensor):
        # reshape input data into 2D tensor
        x_arg = x.reshape(-1, x.shape[-1])
        M, N = x_arg.shape

        MAX_FUSED_SIZE = 65536 // x.element_size()
        BLOCK_SIZE_N = min(MAX_FUSED_SIZE, triton.next_power_of_2(N))
        if N > BLOCK_SIZE_N:
            raise RuntimeError("This layer norm doesn't support feature dim >= 64KB.")

        # heuristics for number of warps.
        num_warps = min(max(BLOCK_SIZE_N // 256, 1), 8)

        mean = torch.zeros((M,)).cuda()
        var = torch.zeros((M,)).cuda()

        # enqueue kernel
        # fmt: off
        k_mean[(M,)](
            x_arg, mean, var,
            x_arg.stride(0),
            N,
            num_warps=num_warps,
            BLOCK_SIZE_N=BLOCK_SIZE_N
        )
        # fmt: on

        return mean.reshape(x.shape[:-1]), var.reshape(x.shape[:-1])

    def test_mean():
        torch.random.manual_seed(0)
        a = torch.rand((4, 2048, 384), device=torch.device("cuda"))

        mean, var = stats(a)
        t_mean = torch.mean(a, dim=-1)
        t_var = torch.var(a, dim=-1)

        print(mean)
        print(t_mean)
        print(var)
        print(t_var)

        assert torch.allclose(mean, t_mean, rtol=1e-1)
        assert torch.allclose(var, t_var, rtol=1e-1)
