# Copyright (c) 2024 Zenteiq Aitech Innovations Private Limited and
# AiREX Lab, Indian Institute of Science, Bangalore.
# All rights reserved.
#
# This file is part of SciREX
# (Scientific Research and Engineering eXcellence Platform),
# developed jointly by Zenteiq Aitech Innovations and AiREX Lab
# under the guidance of Prof. Sashikumaar Ganesan.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For any clarifications or special considerations,
# please contact: contact@scirex.org

"""Neural Network Model Implementation for Physics-Informed Neural Networks.

This module implements the neural network architecture and training loop for
solving PDEs using physics-informed neural networks (VPINNs).
It provides a flexible framework for handling various PDEs through custom
loss functions.

The implementation supports:
    - Flexible neural network architectures
    - Dirichlet boundary conditions
    - Custom loss function composition
    - Adaptive learning rate scheduling
    - Automatic differentiation for gradients

Key classes:
    - DenseModel: Neural network model for VPINN implementation

Authors:
    - Divij Ghose (https://divijghose.github.io/)

Versions:
    - 27-Dec-2024 (Version 0.1): Initial Implementation
"""
import tensorflow as tf
from tensorflow.keras import layers
from tensorflow.keras import initializers
import copy
import numpy as np

# import tensorflow wrapper
from ....dl.tensorflow_wrapper import TensorflowDense
from ..optimizers.lbfgs import LBFGSHelper


# Custom Model
class DenseModel(tf.keras.Model):
    """Neural network model for solving PDEs using PINNs.

    This class implements a custom neural network architecture for solving
    partial differential equations using Physics Informed Neural Networks.
    It supports flexible layer configurations and various loss components.

    Attributes:
        layer_dims: List of neurons per layer including input/output
        learning_rate_dict: Learning rate configuration containing:
            - initial_learning_rate: Starting learning rate
            - use_lr_scheduler: Whether to use learning rate decay
            - decay_steps: Steps between learning rate updates
            - decay_rate: Factor for learning rate decay
        loss_function: Custom loss function for PDE residuals
        input_tensors_list: List containing:
            [0]: input_tensor - Main computation points
            [1]: dirichlet_input - Boundary points
            [2]: dirichlet_actual - Boundary values
        tensor_dtype: TensorFlow data type for computations
        use_attention: Whether to use attention mechanism
        activation: Activation function for hidden layers
        optimizer: Adam optimizer with optional learning rate schedule

    Example:
        >>> model = DenseModel(
        ...     layer_dims=[2, 64, 64, 1],
        ...     learning_rate_dict={'initial_learning_rate': 0.001},
        ...     loss_function=custom_loss,
        ...     tensor_dtype=tf.float32
        ... )
        >>> history = model.fit(x_train, epochs=1000)

    Note:
        The training process balances PDE residuals and boundary conditions
        through a weighted loss function.
    """

    def __init__(
        self,
        layer_dims: list,
        learning_rate_dict: dict,
        loss_function,
        input_tensors_list: list,
        force_function_values,
        tensor_dtype,
        use_attention=False,
        activation="tanh",
        hessian=False,
    ):
        """
        Initialize the DenseModel class.

        Args:
            layer_dims (list): List of neurons per layer including input/output.
            learning_rate_dict (dict): Learning rate configuration containing:
                - initial_learning_rate: Starting learning rate
                - use_lr_scheduler: Whether to use learning rate decay
                - decay_steps: Steps between learning rate updates
                - decay_rate: Factor for learning rate decay

            loss_function: Custom loss function for PDE residuals
            input_tensors_list: List containing:
                [0]: input_tensor - Main computation points
                [1]: dirichlet_input - Boundary points
                [2]: dirichlet_actual - Boundary values
            force_function_values: Tensor containing:
                - forcing_function: Forcing function values
            tensor_dtype: TensorFlow data type for computations
            use_attention (bool): Whether to use attention mechanism, defaults to False.
            activation (str): Activation function for hidden layers, defaults to "tanh".
            hessian (bool): Whether to compute Hessian matrix, defaults to False.

        Returns:
            None
        """
        super(DenseModel, self).__init__()
        self.layer_dims = layer_dims
        self.use_attention = use_attention
        self.activation = activation
        self.layer_list = []
        self.loss_function = loss_function
        self.hessian = hessian

        self.tensor_dtype = tensor_dtype

        # if dtype is not a valid tensorflow dtype, raise an error
        if not isinstance(self.tensor_dtype, tf.DType):
            raise TypeError("The given dtype is not a valid tensorflow dtype")

        self.force_function_values = force_function_values

        self.input_tensors_list = input_tensors_list
        self.input_tensor = copy.deepcopy(input_tensors_list[0])
        self.dirichlet_input = copy.deepcopy(input_tensors_list[1])
        self.dirichlet_actual = copy.deepcopy(input_tensors_list[2])
        self.initial_Ez_input = copy.deepcopy(input_tensors_list[3])
        self.initial_Ez_actual = copy.deepcopy(input_tensors_list[4])
        self.initial_Hx_input = copy.deepcopy(input_tensors_list[5])
        self.initial_Hx_actual = copy.deepcopy(input_tensors_list[6])
        self.initial_Hy_input = copy.deepcopy(input_tensors_list[7])
        self.initial_Hy_actual = copy.deepcopy(input_tensors_list[8])

        self.force_matrix = self.force_function_values

        print(f"{'-'*74}")
        print(f"| {'PARAMETER':<25} | {'SHAPE':<25} |")
        print(f"{'-'*74}")
        print(
            f"| {'input_tensor':<25} | {str(self.input_tensor.shape):<25} | {self.input_tensor.dtype}"
        )
        print(
            f"| {'force_matrix':<25} | {str(self.force_matrix.shape):<25} | {self.force_matrix.dtype}"
        )
        print(
            f"| {'dirichlet_input':<25} | {str(self.dirichlet_input.shape):<25} | {self.dirichlet_input.dtype}"
        )
        print(
            f"| {'dirichlet_actual':<25} | {str(self.dirichlet_actual.shape):<25} | {self.dirichlet_actual.dtype}"
        )
        print(f"{'-'*74}")

        ## ----------------------------------------------------------------- ##
        ## ---------- LEARNING RATE AND OPTIMISER FOR THE MODEL ------------ ##
        ## ----------------------------------------------------------------- ##

        # parse the learning rate dictionary
        self.learning_rate_dict = learning_rate_dict
        initial_learning_rate = learning_rate_dict["initial_learning_rate"]
        use_lr_scheduler = learning_rate_dict["use_lr_scheduler"]
        decay_steps = learning_rate_dict["decay_steps"]
        decay_rate = learning_rate_dict["decay_rate"]
        # staircase = learning_rate_dict["staircase"]

        if use_lr_scheduler:
            learning_rate_fn = tf.keras.optimizers.schedules.ExponentialDecay(
                initial_learning_rate, decay_steps, decay_rate, staircase=True
            )
        else:
            learning_rate_fn = initial_learning_rate

        self.epoch = 0
        self.initial_learning_rate = initial_learning_rate
        self.learning_rate_fn = learning_rate_fn
        self.use_lr_scheduler = use_lr_scheduler
        self.decay_steps = decay_steps
        self.decay_rate = decay_rate

        # Initialize with Adam optimizer
        self.optimizer = tf.keras.optimizers.Adam(learning_rate=self.learning_rate_fn)

        ## ----------------------------------------------------------------- ##
        ## --------------------- MODEL ARCHITECTURE ------------------------ ##
        ## ----------------------------------------------------------------- ##

        # Build dense layers based on the input list
        for dim in range(len(self.layer_dims) - 2):
            # Try Xavier initialization with a smaller scale
            kernel_initializer = tf.keras.initializers.GlorotUniform(seed=42)
            tf.print(f"Adding Dense Layer with {self.layer_dims[dim + 1]} units")
            self.layer_list.append(
                TensorflowDense.create_layer(
                    units=self.layer_dims[dim + 1],
                    activation="tanh",
                    dtype=tf.float32,
                    kernel_initializer=kernel_initializer,
                    bias_initializer="zeros",
                )
            )

        # Add a output layer with no activation
        self.layer_list.append(
            TensorflowDense.create_layer(
                units=self.layer_dims[-1],
                activation=None,
                dtype=tf.float32,
                kernel_initializer="glorot_uniform",
                bias_initializer="zeros",
            )
        )

        # Compile the model
        self.compile(optimizer=self.optimizer)
        self.build(input_shape=(None, self.layer_dims[0]))

        # print the summary of the model
        self.summary()

    # def build(self, input_shape):
    #     super(DenseModel, self).build(input_shape)

    def call(self, inputs) -> tf.Tensor:
        """
        The call method for the model.

        Args:
            inputs: The input tensor for the model.

        Returns:
            tf.Tensor: The output tensor from the model.
        """
        x = inputs

        # Apply attention layer after input if flag is True
        if self.use_attention:
            x = self.attention_layer([x, x])

        # Loop through the dense layers
        for layer in self.layer_list:
            x = layer(x)

        return x

    @tf.function
    def train_step(
        self, beta_boundary=10.0, beta_initial=100.0, bilinear_params_dict=None
    ) -> dict:
        with tf.GradientTape(persistent=True) as tape:
            # Predict boundary values
            predicted_values_dirichlet = self(self.dirichlet_input, training=True)[
                :, 0:1
            ]
            predicted_values_initial_Ez = self(self.initial_Ez_input, training=True)[
                :, 0:1
            ]
            predicted_values_initial_Hx = self(self.initial_Hx_input, training=True)[
                :, 1:2
            ]
            predicted_values_initial_Hy = self(self.initial_Hy_input, training=True)[
                :, 2:3
            ]

            total_loss = 0.0

            with tf.GradientTape(persistent=True) as tape1:
                tape1.watch(self.input_tensor)

                predicted_values = self(self.input_tensor, training=True)

                Ez = predicted_values[:, 0:1]
                Hx = predicted_values[:, 1:2]
                Hy = predicted_values[:, 2:3]

            grad_Ez = tape1.gradient(Ez, self.input_tensor)
            grad_Hx = tape1.gradient(Hx, self.input_tensor)
            grad_Hy = tape1.gradient(Hy, self.input_tensor)

            grad_x_Ez = grad_Ez[:, 0:1]
            grad_y_Ez = grad_Ez[:, 1:2]
            grad_t_Ez = grad_Ez[:, 2:3]

            grad_x_Hx = grad_Hx[:, 0:1]
            grad_y_Hx = grad_Hx[:, 1:2]
            grad_t_Hx = grad_Hx[:, 2:3]

            grad_x_Hy = grad_Hy[:, 0:1]
            grad_y_Hy = grad_Hy[:, 1:2]
            grad_t_Hy = grad_Hy[:, 2:3]

            pde_residual = self.loss_function(
                pred_nn_Ez=Ez,
                pred_nn_Hx=Hx,
                pred_nn_Hy=Hy,
                pred_grad_x_nn_Ez=grad_x_Ez,
                pred_grad_x_nn_Hx=grad_x_Hx,
                pred_grad_x_nn_Hy=grad_x_Hy,
                pred_grad_y_nn_Ez=grad_y_Ez,
                pred_grad_y_nn_Hx=grad_y_Hx,
                pred_grad_y_nn_Hy=grad_y_Hy,
                pred_grad_t_nn_Ez=grad_t_Ez,
                pred_grad_t_nn_Hx=grad_t_Hx,
                pred_grad_t_nn_Hy=grad_t_Hy,
                forcing_function_1=self.force_matrix,
                forcing_function_2=self.force_matrix,
                forcing_function_3=self.force_matrix,
                bilinear_params=bilinear_params_dict,
            )

            # Boundary conditions
            boundary_loss = tf.reduce_mean(
                tf.square(predicted_values_dirichlet - self.dirichlet_actual)
            )

            initial_Ez_loss = tf.reduce_mean(
                tf.square(predicted_values_initial_Ez - self.initial_Ez_actual)
            )

            initial_Hx_loss = tf.reduce_mean(
                tf.square(predicted_values_initial_Hx - self.initial_Hx_actual)
            )

            initial_Hy_loss = tf.reduce_mean(
                tf.square(predicted_values_initial_Hy - self.initial_Hy_actual)
            )

            total_loss = (
                pde_residual
                + beta_boundary * boundary_loss
                + beta_initial * (initial_Ez_loss + initial_Hx_loss + initial_Hy_loss)
            )
            # tf.print(f"PDE Residual Shape: {pde_residual.shape}")
            # tf.print(f"Boundary Loss Shape: {boundary_loss.shape}")
            # tf.print(f"Initial Loss Shape: {initial_Ez_loss.shape}")

        trainable_vars = self.trainable_variables
        self.gradients = tape.gradient(total_loss, trainable_vars)
        self.optimizer.apply_gradients(zip(self.gradients, trainable_vars))

        return {
            "loss_pde": pde_residual,
            "loss_dirichlet": boundary_loss,
            "loss_initial": initial_Ez_loss + initial_Hx_loss + initial_Hy_loss,
            "loss": total_loss,
        }