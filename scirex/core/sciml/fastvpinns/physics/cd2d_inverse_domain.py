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

"""Loss Function Implementation for Convection-Diffusion 2D Inverse Problems.

This module implements the loss function for solving inverse problems in 2D
convection-diffusion equations using neural networks. It focuses on computing
residuals in the weak form of the PDE for parameter identification.


Key functions:
    - pde_loss_cd2d_inverse_domain: Computes domain-based PDE loss

Note:
    The implementation is based on the FastVPINNs methodology [1] for efficient computation of Variational residuals of PDEs.

References:
    [1] FastVPINNs: Tensor-Driven Acceleration of VPINNs for Complex Geometries 
    DOI: https://arxiv.org/abs/2404.12063
"""

import tensorflow as tf


# PDE loss function for the CD2D inverse problem (Domain)
def pde_loss_cd2d_inverse_domain(
    test_shape_val_mat: tf.Tensor,
    test_grad_x_mat: tf.Tensor,
    test_grad_y_mat: tf.Tensor,
    pred_nn: tf.Tensor,
    pred_grad_x_nn: tf.Tensor,
    pred_grad_y_nn: tf.Tensor,
    forcing_function: callable,
    bilinear_params: dict,
    inverse_params_list: list,
) -> tf.Tensor:
    """Computes domain-based loss for 2D convection-diffusion inverse problem.

    Implements the weak form residual calculation for parameter identification
    in 2D convection-diffusion equations. The loss includes diffusion,
    convection, and reaction terms.

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
            - b_x: x-direction convection coefficient
            - b_y: y-direction convection coefficient
            - c: reaction coefficient
        inverse_params_list: List containing:
            - diffusion coefficient neural network

    Returns:
        Cell-wise residuals averaged over test functions
            Shape: (n_cells,)

    Notes:
        The weak form includes:
        - Diffusion term: ∫ε∇u·∇v dΩ
        - Convection term: ∫(b·∇u)v dΩ
        - Reaction term: ∫cuv dΩ
        where ε is the diffusion coefficient to be identified.
    """

    # The first values in the inverse_params_list is the number of inverse problems
    diffusion_coeff_NN = inverse_params_list[0]

    # ∫ε.du/dx. dv/dx dΩ
    pde_diffusion_x = tf.transpose(
        tf.linalg.matvec(test_grad_x_mat, pred_grad_x_nn * diffusion_coeff_NN)
    )

    # ∫ε.du/dy. dv/dy dΩ
    pde_diffusion_y = tf.transpose(
        tf.linalg.matvec(test_grad_y_mat, pred_grad_y_nn * diffusion_coeff_NN)
    )

    # eps * ∫ (du/dx. dv/dx + du/dy. dv/dy) dΩ
    # Here our eps is a variable which is to be learned, Which is already premultiplied with the predicted gradient of the neural network
    pde_diffusion = pde_diffusion_x + pde_diffusion_y

    # ∫du/dx. v dΩ
    conv_x = tf.transpose(tf.linalg.matvec(test_shape_val_mat, pred_grad_x_nn))

    # # ∫du/dy. v dΩ
    conv_y = tf.transpose(tf.linalg.matvec(test_shape_val_mat, pred_grad_y_nn))

    # # b(x) * ∫du/dx. v dΩ + b(y) * ∫du/dy. v dΩ
    conv = bilinear_params["b_x"] * conv_x + bilinear_params["b_y"] * conv_y

    # reaction term
    # ∫c.u.v dΩ
    reaction = bilinear_params["c"] * tf.transpose(
        tf.linalg.matvec(test_shape_val_mat, pred_nn)
    )

    residual_matrix = (pde_diffusion + conv + reaction) - forcing_function

    # Perform Reduce mean along the axis 0
    residual_cells = tf.reduce_mean(tf.square(residual_matrix), axis=0)

    return residual_cells