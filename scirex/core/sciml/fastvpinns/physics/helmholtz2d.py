# Copyright (c) 2024 Zenteiq Aitech Innovations Private Limited and AiREX Lab,
# Indian Institute of Science, Bangalore.
# All rights reserved.
#
# This file is part of SciREX
# (Scientific Research and Engineering eXcellence Platform),
# developed jointly by Zenteiq Aitech Innovations and AiREX Lab
# under the guidance of Prof. Sashikumaar Ganesan.
#
# SciREX is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SciREX is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with SciREX. If not, see <https://www.gnu.org/licenses/>.
#
# For any clarifications or special considerations,
# please contact <scirex@zenteiq.ai>


"""Loss Function Implementation for 2D Helmholtz Problem.

This module implements the loss function for solving the 2D Helmholtz equation
using neural networks. It focuses on computing residuals in the weak form 
of the PDE with wave number parameter.


Key functions:
    - pde_loss_helmholtz: Computes domain-based PDE loss

Note:
    The implementation is based on the FastVPINNs methodology [1] for efficient
    computation of Variational residuals of PDEs.

References:
    [1] FastVPINNs: Tensor-Driven Acceleration of VPINNs for Complex Geometries
        DOI: https://arxiv.org/abs/2404.12063
"""

import tensorflow as tf


def pde_loss_helmholtz(
    test_shape_val_mat: tf.Tensor,
    test_grad_x_mat: tf.Tensor,
    test_grad_y_mat: tf.Tensor,
    pred_nn: tf.Tensor,
    pred_grad_x_nn: tf.Tensor,
    pred_grad_y_nn: tf.Tensor,
    forcing_function: callable,
    bilinear_params: dict,
) -> tf.Tensor:
    """Calculates residual for 2D Helmholtz equation.

    Implements the FastVPINNs methodology for computing variational residuals
    in 2D Helmholtz equation (-Δu - k²u = f) using efficient tensor operations.

    Args:
        test_shape_val_mat: Test function values at quadrature points
            Shape: (n_elements, n_test_functions, n_quad_points)
        test_grad_x_mat: Test function x-derivatives at quadrature points
            Shape: (n_elements, n_test_functions, n_quad_points)
        test_grad_y_mat: Test function y-derivatives at quadrature points
            Shape: (n_elements, n_test_functions, n_quad_points)
        pred_nn: Neural network solution at quadrature points
            Shape: (n_elements, n_quad_points)
        pred_grad_x_nn: x-derivative of NN solution at quadrature points
            Shape: (n_elements, n_quad_points)
        pred_grad_y_nn: y-derivative of NN solution at quadrature points
            Shape: (n_elements, n_quad_points)
        forcing_function: Right-hand side forcing term
        bilinear_params: Dictionary containing:
            eps: Diffusion coefficient (typically 1.0)
            k: Wave number parameter

    Returns:
        Cell-wise residuals averaged over test functions
            Shape: (n_cells,)

    Note:
        The weak form includes:
        - Diffusion term: -∫∇u·∇v dΩ
        - Wave term: ∫k²uv dΩ
        Implementation handles high wave numbers through efficient
        tensor operations.
    """
    #  ∫ (du/dx. dv/dx ) dΩ
    pde_diffusion_x = tf.transpose(tf.linalg.matvec(test_grad_x_mat, pred_grad_x_nn))

    #  ∫ (du/dy. dv/dy ) dΩ
    pde_diffusion_y = tf.transpose(tf.linalg.matvec(test_grad_y_mat, pred_grad_y_nn))

    # eps * ∫ (du/dx. dv/dx + du/dy. dv/dy) dΩ
    pde_diffusion = bilinear_params["eps"] * (pde_diffusion_x + pde_diffusion_y)

    # \int(k^2 (u).v) dw
    helmholtz_additional = (bilinear_params["k"] ** 2) * tf.transpose(
        tf.linalg.matvec(test_shape_val_mat, pred_nn)
    )

    residual_matrix = -1.0 * (pde_diffusion) + helmholtz_additional - forcing_function

    residual_cells = tf.reduce_mean(tf.square(residual_matrix), axis=0)

    return residual_cells