#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division

import numpy as np
import tensorflow as tf

from .base import *
from .utils import maybe_explicit_broadcast


__all__ = [
    'Normal',
    'Bernoulli',
    'Categorical',
    'Discrete',
    'Uniform',
    'Gamma',
    'Beta',
    'Poisson',
    'Binomial',
]


class Normal(Distribution):
    """
    The class of univariate Normal distribution.
    See :class:`~zhusuan.distributions.base.Distribution` for details.

    :param mean: A `float32` Tensor. The mean of the Normal distribution.
        Should be broadcastable to match `logstd`.
    :param logstd: A `float32` Tensor. The log standard deviation of the Normal
        distribution. Should be broadcastable to match `mean`.
    :param group_event_ndims: A 0-D `int32` Tensor representing the number of
        dimensions in `batch_shape` (counted from the end) that are grouped
        into a single event, so that their probabilities are calculated
        together. Default is 0, which means a single value is an event.
        See :class:`~zhusuan.distributions.base.Distribution` for more detailed 
        explanation.
    :param is_reparameterized: A Bool. If True, gradients on samples from this
        distribution are allowed to propagate into inputs, using the
        reparametrization trick from (Kingma, 2013).
    :param check_numerics: Bool. Whether to check numeric issues.
    """

    def __init__(self,
                 mean=0.,
                 logstd=0.,
                 group_event_ndims=0,
                 is_reparameterized=True,
                 check_numerics=False):
        self._mean = tf.convert_to_tensor(mean, dtype=tf.float32)
        self._logstd = tf.convert_to_tensor(logstd, dtype=tf.float32)
        try:
            tf.broadcast_static_shape(self._mean.get_shape(),
                                      self._logstd.get_shape())
        except ValueError:
            raise ValueError(
                "mean and logstd should be broadcastable to match each "
                "other. ({} vs. {})".format(
                    self._mean.get_shape(), self._logstd.get_shape()))
        self._check_numerics = check_numerics
        super(Normal, self).__init__(
            dtype=tf.float32,
            is_continuous=True,
            is_reparameterized=is_reparameterized,
            group_event_ndims=group_event_ndims)

    @property
    def mean(self):
        """The mean of the Normal distribution."""
        return self._mean

    @property
    def logstd(self):
        """The log standard deviation of the Normal distribution."""
        return self._logstd

    def _value_shape(self):
        return tf.constant([], dtype=tf.int32)

    def _get_value_shape(self):
        return tf.TensorShape([])

    def _batch_shape(self):
        return tf.broadcast_dynamic_shape(tf.shape(self.mean),
                                          tf.shape(self.logstd))

    def _get_batch_shape(self):
        return tf.broadcast_static_shape(self.mean.get_shape(),
                                         self.logstd.get_shape())

    def _sample(self, n_samples):
        mean, logstd = self.mean, self.logstd
        if not self.is_reparameterized:
            mean = tf.stop_gradient(mean)
            logstd = tf.stop_gradient(logstd)
        shape = tf.concat([[n_samples], self.batch_shape], 0)
        samples = tf.random_normal(shape) * tf.exp(logstd) + mean
        static_n_samples = n_samples if isinstance(n_samples, int) else None
        samples.set_shape(
            tf.TensorShape([static_n_samples]).concatenate(
                self.get_batch_shape()))
        return samples

    def _log_prob(self, given):
        c = -0.5 * np.log(2 * np.pi)
        precision = tf.exp(-2 * self.logstd)
        if self._check_numerics:
            with tf.control_dependencies(
                    [tf.check_numerics(precision, "precision")]):
                precision = tf.identity(precision)
        return c - self.logstd - 0.5 * precision * tf.square(given - self.mean)

    def _prob(self, given):
        return tf.exp(self._log_prob(given))


class Bernoulli(Distribution):
    """
    The class of univariate Bernoulli distribution.
    See :class:`~zhusuan.distributions.base.Distribution` for details.

    :param logits: A `float32` Tensor. The log-odds of probabilities of
        being 1.

        .. math:: \\mathrm{logits} = \\log \\frac{p}{1 - p}

    :param group_event_ndims: A 0-D `int32` Tensor representing the number of
        dimensions in `batch_shape` (counted from the end) that are grouped
        into a single event, so that their probabilities are calculated
        together. Default is 0, which means a single value is an event.
        See :class:`~zhusuan.distributions.base.Distribution` for more detailed
        explanation.
    """

    def __init__(self, logits, group_event_ndims=0):
        self._logits = tf.convert_to_tensor(logits, dtype=tf.float32)
        super(Bernoulli, self).__init__(
            dtype=tf.int32,
            is_continuous=False,
            is_reparameterized=False,
            group_event_ndims=group_event_ndims)

    @property
    def logits(self):
        """The log-odds of probabilities of being 1."""
        return self._logits

    def _value_shape(self):
        return tf.constant([], dtype=tf.int32)

    def _get_value_shape(self):
        return tf.TensorShape([])

    def _batch_shape(self):
        return tf.shape(self.logits)

    def _get_batch_shape(self):
        return self.logits.get_shape()

    def _sample(self, n_samples):
        p = tf.sigmoid(self.logits)
        shape = tf.concat([[n_samples], self.batch_shape], 0)
        alpha = tf.random_uniform(shape, minval=0, maxval=1)
        samples = tf.cast(tf.less(alpha, p), dtype=self.dtype)
        static_n_samples = n_samples if isinstance(n_samples, int) else None
        samples.set_shape(
            tf.TensorShape([static_n_samples]).concatenate(
                self.get_batch_shape()))
        return samples

    def _log_prob(self, given):
        given, logits = maybe_explicit_broadcast(
            tf.to_float(given), self.logits, 'given', 'logits')
        return -tf.nn.sigmoid_cross_entropy_with_logits(labels=given,
                                                        logits=logits)

    def _prob(self, given):
        return tf.exp(self._log_prob(given))


class Categorical(Distribution):
    """
    The class of univariate Categorical distribution.
    See :class:`~zhusuan.distributions.base.Distribution` for details.

    :param logits: A N-D (N >= 1) `float32` Tensor of shape (...,
        n_categories). Each slice `[i, j,..., k, :]` represents the
        un-normalized log probabilities for all categories.

        .. math:: \\mathrm{logits} \\propto \\log p

    :param group_event_ndims: A 0-D `int32` Tensor representing the number of
        dimensions in `batch_shape` (counted from the end) that are grouped
        into a single event, so that their probabilities are calculated
        together. Default is 0, which means a single value is an event.
        See :class:`~zhusuan.distributions.base.Distribution` for more detailed 
        explanation.

    A single sample is a (N-1)-D Tensor with `tf.int32` values in range
    [0, n_categories).
    """

    def __init__(self, logits, group_event_ndims=0):
        self._logits = tf.convert_to_tensor(logits, dtype=tf.float32)
        static_logits_shape = self._logits.get_shape()
        shape_err_msg = "logits should have rank >= 1."
        if static_logits_shape and (static_logits_shape.ndims < 1):
            raise ValueError(shape_err_msg)
        elif static_logits_shape and (
                static_logits_shape[-1].value is not None):
            self._n_categories = static_logits_shape[-1].value
        else:
            _assert_shape_op = tf.assert_rank_at_least(
                self._logits, 1, message=shape_err_msg)
            with tf.control_dependencies([_assert_shape_op]):
                self._logits = tf.identity(self._logits)
            self._n_categories = tf.shape(self._logits)[-1]

        # TODO: add type argument for distributions
        super(Categorical, self).__init__(
            dtype=tf.int32,
            is_continuous=False,
            is_reparameterized=False,
            group_event_ndims=group_event_ndims)

    @property
    def logits(self):
        """The un-normalized log probabilities."""
        return self._logits

    @property
    def n_categories(self):
        """The number of categories in the distribution."""
        return self._n_categories

    def _value_shape(self):
        return tf.constant([], dtype=tf.int32)

    def _get_value_shape(self):
        return tf.TensorShape([])

    def _batch_shape(self):
        return tf.shape(self.logits)[:-1]

    def _get_batch_shape(self):
        if self.logits.get_shape():
            return self.logits.get_shape()[:-1]
        return tf.TensorShape(None)

    def _sample(self, n_samples):
        if self.logits.get_shape().ndims == 2:
            logits_flat = self.logits
        else:
            logits_flat = tf.reshape(self.logits, [-1, self.n_categories])
        samples_flat = tf.transpose(tf.multinomial(logits_flat, n_samples))
        if self.logits.get_shape().ndims == 2:
            return samples_flat
        shape = tf.concat([[n_samples], self.batch_shape], 0)
        samples = tf.reshape(samples_flat, shape)
        static_n_samples = n_samples if isinstance(n_samples, int) else None
        samples.set_shape(
            tf.TensorShape([static_n_samples]).concatenate(
                self.get_batch_shape()))
        return samples

    def _log_prob(self, given):
        logits = self.logits

        def _broadcast(given, logits):
            # static shape has been checked in base class.
            ones_ = tf.ones(tf.shape(logits)[:-1], tf.int32)
            if logits.get_shape():
                ones_.set_shape(logits.get_shape()[:-1])
            given *= ones_
            logits *= tf.ones_like(tf.expand_dims(given, -1), tf.float32)
            return given, logits

        def _is_same_dynamic_shape(given, logits):
            return tf.cond(
                tf.equal(tf.rank(given), tf.rank(logits) - 1),
                lambda: tf.reduce_all(tf.equal(
                    tf.concat([tf.shape(given), tf.shape(logits)[:-1]], 0),
                    tf.concat([tf.shape(logits)[:-1], tf.shape(given)], 0))),
                lambda: tf.convert_to_tensor(False, tf.bool))

        if not (given.get_shape() and logits.get_shape()):
            given, logits = _broadcast(given, logits)
        else:
            if given.get_shape().ndims != logits.get_shape().ndims - 1:
                given, logits = _broadcast(given, logits)
            elif given.get_shape().is_fully_defined() and \
                    logits.get_shape()[:-1].is_fully_defined():
                if given.get_shape() != logits.get_shape()[:-1]:
                    given, logits = _broadcast(given, logits)
            else:
                # Below code seems to induce a BUG when this function is
                # called in HMC. Probably due to tensorflow's not supporting
                # control flow edge from an op inside the body to outside.
                # We should further fix this.
                #
                # given, logits = tf.cond(
                #     is_same_dynamic_shape(given, logits),
                #     lambda: (given, logits),
                #     lambda: _broadcast(given, logits, 'given', 'logits'))
                given, logits = _broadcast(given, logits)
        log_p = -tf.nn.sparse_softmax_cross_entropy_with_logits(labels=given,
                                                                logits=logits)
        if given.get_shape() and logits.get_shape():
            log_p.set_shape(tf.broadcast_static_shape(given.get_shape(),
                                                      logits.get_shape()[:-1]))
        return log_p

    def _prob(self, given):
        return tf.exp(self._log_prob(given))


Discrete = Categorical


class Uniform(Distribution):
    """
    The class of univariate Uniform distribution.
    See :class:`~zhusuan.distributions.base.Distribution` for details.

    :param minval: A `float32` Tensor. The lower bound on the range of the
        uniform distribution. Should be broadcastable to match `maxval`.
    :param maxval: A `float32` Tensor. The upper bound on the range of the
        uniform distribution. Should be element-wise bigger than `minval`.
    :param group_event_ndims: A 0-D `int32` Tensor representing the number of
        dimensions in `batch_shape` (counted from the end) that are grouped
        into a single event, so that their probabilities are calculated
        together. Default is 0, which means a single value is an event.
        See :class:`~zhusuan.distributions.base.Distribution` for more detailed
        explanation.
    :param is_reparameterized: A Bool. If True, gradients on samples from this
        distribution are allowed to propagate into inputs, using the
        reparametrization trick from (Kingma, 2013).
    :param check_numerics: Bool. Whether to check numeric issues.
    """

    def __init__(self,
                 minval=0.,
                 maxval=1.,
                 group_event_ndims=0,
                 is_reparameterized=True,
                 check_numerics=False):
        self._minval = tf.convert_to_tensor(minval, dtype=tf.float32)
        self._maxval = tf.convert_to_tensor(maxval, dtype=tf.float32)
        try:
            tf.broadcast_static_shape(self._minval.get_shape(),
                                      self._maxval.get_shape())
        except ValueError:
            raise ValueError(
                "minval and maxval should be broadcastable to match each "
                "other. ({} vs. {})".format(
                    self._minval.get_shape(), self._maxval.get_shape()))
        self._check_numerics = check_numerics
        super(Uniform, self).__init__(
            dtype=tf.float32,
            is_continuous=True,
            is_reparameterized=is_reparameterized,
            group_event_ndims=group_event_ndims)

    @property
    def minval(self):
        """The lower bound on the range of the uniform distribution."""
        return self._minval

    @property
    def maxval(self):
        """The upper bound on the range of the uniform distribution."""
        return self._maxval

    def _value_shape(self):
        return tf.constant([], tf.float32)

    def _get_value_shape(self):
        return tf.TensorShape([])

    def _batch_shape(self):
        return tf.broadcast_dynamic_shape(tf.shape(self.minval),
                                          tf.shape(self.maxval))

    def _get_batch_shape(self):
        return tf.broadcast_static_shape(self.minval.get_shape(),
                                         self.maxval.get_shape())

    def _sample(self, n_samples):
        minval, maxval = self.minval, self.maxval
        if not self.is_reparameterized:
            minval = tf.stop_gradient(minval)
            maxval = tf.stop_gradient(maxval)
        shape = tf.concat([[n_samples], self.batch_shape], 0)
        samples = tf.random_uniform(shape, 0, 1) * (maxval - minval) + minval
        static_n_samples = n_samples if isinstance(n_samples, int) else None
        samples.set_shape(
            tf.TensorShape([static_n_samples]).concatenate(
                self.get_batch_shape()))
        return samples

    def _log_prob(self, given):
        log_p = tf.log(self._prob(given))
        if self._check_numerics:
            with tf.control_dependencies(
                    [tf.check_numerics(log_p, message="log_p")]):
                log_p = tf.identity(log_p)
        return log_p

    def _prob(self, given):
        mask = tf.cast(tf.logical_and(tf.less_equal(self.minval, given),
                                      tf.less(given, self.maxval)),
                       tf.float32)
        p = 1. / (self.maxval - self.minval)
        if self._check_numerics:
            with tf.control_dependencies(
                    [tf.check_numerics(p, message="p")]):
                p = tf.identity(p)
        return p * mask


class Gamma(Distribution):
    """
    The class of univariate Gamma distribution.
    See :class:`~zhusuan.distributions.base.Distribution` for details.

    :param alpha: A `float32` Tensor. The shape parameter of the Gamma
        distribution. Should be positive and broadcastable to match `beta`.
    :param beta: A `float32` Tensor. The inverse scale parameter of the Gamma
        distribution. Should be positive and broadcastable to match `alpha`.
    :param group_event_ndims: A 0-D `int32` Tensor representing the number of
        dimensions in `batch_shape` (counted from the end) that are grouped
        into a single event, so that their probabilities are calculated
        together. Default is 0, which means a single value is an event.
        See :class:`~zhusuan.distributions.base.Distribution` for more detailed
        explanation.
    :param check_numerics: Bool. Whether to check numeric issues.
    """

    def __init__(self,
                 alpha,
                 beta,
                 group_event_ndims=0,
                 check_numerics=False):
        self._alpha = tf.convert_to_tensor(alpha, dtype=tf.float32)
        self._beta = tf.convert_to_tensor(beta, dtype=tf.float32)
        try:
            tf.broadcast_static_shape(self._alpha.get_shape(),
                                      self._beta.get_shape())
        except ValueError:
            raise ValueError(
                "alpha and beta should be broadcastable to match each "
                "other. ({} vs. {})".format(
                    self._alpha.get_shape(), self._beta.get_shape()))
        self._check_numerics = check_numerics
        super(Gamma, self).__init__(
            dtype=tf.float32,
            is_continuous=True,
            is_reparameterized=False,
            group_event_ndims=group_event_ndims)

    @property
    def alpha(self):
        """The shape parameter of the Gamma distribution."""
        return self._alpha

    @property
    def beta(self):
        """The inverse scale parameter of the Gamma distribution."""
        return self._beta

    def _value_shape(self):
        return tf.constant([], dtype=tf.int32)

    def _get_value_shape(self):
        return tf.TensorShape([])

    def _batch_shape(self):
        return tf.broadcast_dynamic_shape(tf.shape(self.alpha),
                                          tf.shape(self.beta))

    def _get_batch_shape(self):
        return tf.broadcast_static_shape(self.alpha.get_shape(),
                                         self.beta.get_shape())

    def _sample(self, n_samples):
        return tf.random_gamma([n_samples], self.alpha, beta=self.beta)

    def _log_prob(self, given):
        alpha, beta = self.alpha, self.beta
        log_given = tf.log(given)
        log_alpha, log_beta = tf.log(alpha), tf.log(beta)
        lgamma_alpha = tf.lgamma(alpha)
        if self._check_numerics:
            with tf.control_dependencies(
                    [tf.check_numerics(log_given, "log(given)"),
                     tf.check_numerics(log_alpha, "log(alpha)"),
                     tf.check_numerics(log_beta, "log(beta)"),
                     tf.check_numerics(lgamma_alpha, "lgamma(alpha)")]):
                log_given = tf.identity(log_given)
        return alpha * log_beta - lgamma_alpha + (alpha - 1) * log_given - \
            beta * given

    def _prob(self, given):
        return tf.exp(self._log_prob(given))


class Beta(Distribution):
    """
    The class of univariate Beta distribution.
    See :class:`~zhusuan.distributions.base.Distribution` for details.

    :param alpha: A `float32` Tensor. One of the two shape parameters of the
        Beta distribution. Should be positive and broadcastable to match
        `beta`.
    :param beta: A `float32` Tensor. One of the two shape parameters of the
        Beta distribution. Should be positive and broadcastable to match
        `alpha`.
    :param group_event_ndims: A 0-D `int32` Tensor representing the number of
        dimensions in `batch_shape` (counted from the end) that are grouped
        into a single event, so that their probabilities are calculated
        together. Default is 0, which means a single value is an event.
        See :class:`~zhusuan.distributions.base.Distribution` for more detailed
        explanation.
    :param check_numerics: Bool. Whether to check numeric issues.
    """

    def __init__(self,
                 alpha,
                 beta,
                 group_event_ndims=0,
                 check_numerics=False):
        self._alpha = tf.convert_to_tensor(alpha, dtype=tf.float32)
        self._beta = tf.convert_to_tensor(beta, dtype=tf.float32)
        try:
            tf.broadcast_static_shape(self._alpha.get_shape(),
                                      self._beta.get_shape())
        except ValueError:
            raise ValueError(
                "alpha and beta should be broadcastable to match each "
                "other. ({} vs. {})".format(
                    self._alpha.get_shape(), self._beta.get_shape()))
        self._check_numerics = check_numerics
        super(Beta, self).__init__(
            dtype=tf.float32,
            is_continuous=True,
            is_reparameterized=False,
            group_event_ndims=group_event_ndims)

    @property
    def alpha(self):
        """One of the two shape parameters of the Beta distribution."""
        return self._alpha

    @property
    def beta(self):
        """One of the two shape parameters of the Beta distribution."""
        return self._beta

    def _value_shape(self):
        return tf.constant([], dtype=tf.int32)

    def _get_value_shape(self):
        return tf.TensorShape([])

    def _batch_shape(self):
        return tf.broadcast_dynamic_shape(tf.shape(self.alpha),
                                          tf.shape(self.beta))

    def _get_batch_shape(self):
        return tf.broadcast_static_shape(self.alpha.get_shape(),
                                         self.beta.get_shape())

    def _sample(self, n_samples):
        alpha, beta = maybe_explicit_broadcast(
            self.alpha, self.beta, 'alpha', 'beta')
        x = tf.random_gamma([n_samples], alpha, beta=1)
        y = tf.random_gamma([n_samples], beta, beta=1)
        return x / (x + y)

    def _log_prob(self, given):
        # TODO: not right when given=0 or 1
        alpha, beta = self.alpha, self.beta
        log_given = tf.log(given)
        log_1_minus_given = tf.log(1 - given)
        lgamma_alpha, lgamma_beta = tf.lgamma(alpha), tf.lgamma(beta)
        lgamma_alpha_plus_beta = tf.lgamma(alpha + beta)
        if self._check_numerics:
            with tf.control_dependencies(
                    [tf.check_numerics(log_given, "log(given)"),
                     tf.check_numerics(log_1_minus_given, "log(1 - given)"),
                     tf.check_numerics(lgamma_alpha, "lgamma(alpha)"),
                     tf.check_numerics(lgamma_beta, "lgamma(beta)"),
                     tf.check_numerics(lgamma_alpha_plus_beta,
                                       "lgamma(alpha + beta)")]):
                log_given = tf.identity(log_given)
        return (alpha - 1) * log_given + (beta - 1) * log_1_minus_given - (
            lgamma_alpha + lgamma_beta - lgamma_alpha_plus_beta)

    def _prob(self, given):
        return tf.exp(self._log_prob(given))


class Poisson(Distribution):
    """
    The class of univariate Poisson distribution.
    See :class:`~zhusuan.distributions.base.Distribution` for details.

    :param rate: A `float32` Tensor. The rate parameter of Poisson
        distribution. Must be positive.
    :param group_event_ndims: A 0-D `int32` Tensor representing the number of
        dimensions in `batch_shape` (counted from the end) that are grouped
        into a single event, so that their probabilities are calculated
        together. Default is 0, which means a single value is an event.
        See :class:`~zhusuan.distributions.base.Distribution` for more detailed
        explanation.
    :param check_numerics: Bool. Whether to check numeric issues.
    """

    def __init__(self,
                 rate,
                 group_event_ndims=0,
                 check_numerics=False):
        self._rate = tf.convert_to_tensor(rate, dtype=tf.float32)
        self._check_numerics = check_numerics

        super(Poisson, self).__init__(
            dtype=tf.int32,
            is_continuous=False,
            is_reparameterized=False,
            group_event_ndims=group_event_ndims)

    @property
    def rate(self):
        """The rate parameter of Poisson."""
        return self._rate

    def _value_shape(self):
        return tf.constant([], dtype=tf.int32)

    def _get_value_shape(self):
        return tf.TensorShape([])

    def _batch_shape(self):
        return tf.shape(self.rate)

    def _get_batch_shape(self):
        return self.rate.get_shape()

    def _sample(self, n_samples):
        # This algorithm to generate random Poisson-distributed numbers is
        # given by Kunth [1]
        # [1]: https://en.wikipedia.org/wiki/
        #      Poisson_distribution#Generating_Poisson-distributed_random_variables
        shape = tf.concat([[n_samples], self.batch_shape], 0)
        static_n_samples = n_samples if isinstance(n_samples, int) else None
        static_shape = tf.TensorShape([static_n_samples]).concatenate(
            self.get_batch_shape())

        enlam = tf.exp(-self.rate)
        x = tf.zeros(shape, dtype=self.dtype)
        prod = tf.ones(shape, dtype=tf.float32)

        def loop_cond(prod, x):
            return tf.reduce_any(tf.greater_equal(prod, enlam))

        def loop_body(prod, x):
            prod *= tf.random_uniform(tf.shape(prod), minval=0, maxval=1)
            x += tf.cast(tf.greater_equal(prod, enlam), dtype=self.dtype)
            return prod, x

        _, samples = tf.while_loop(
            loop_cond, loop_body, loop_vars=[prod, x],
            shape_invariants=[static_shape, static_shape])

        samples.set_shape(static_shape)
        return samples

    def _log_prob(self, given):
        rate = self.rate
        given = tf.to_float(given)

        log_rate = tf.log(rate)
        lgamma_given_plus_1 = tf.lgamma(given + 1)

        if self._check_numerics:
            with tf.control_dependencies(
                    [tf.check_numerics(log_rate, "log(rate)"),
                     tf.check_numerics(lgamma_given_plus_1,
                                       "lgamma(given + 1)")]):
                log_rate = tf.identity(log_rate)
        return given * log_rate - rate - lgamma_given_plus_1

    def _prob(self, given):
        return tf.exp(self._log_prob(given))


class Binomial(Distribution):
    """
    The class of univariate Binomial distribution.
    See :class:`~zhusuan.distributions.base.Distribution` for details.

    :param logits: A `float32` Tensor. The log-odds of probabilities.

        .. math:: \\mathrm{logits} = \\log \\frac{p}{1 - p}

    :param n_experiments: A 0-D `int32` Tensor. The number of experiments
        for each sample.
    :param group_event_ndims: A 0-D `int32` Tensor representing the number of
        dimensions in `batch_shape` (counted from the end) that are grouped
        into a single event, so that their probabilities are calculated
        together. Default is 0, which means a single value is an event.
        See :class:`~zhusuan.distributions.base.Distribution` for more detailed
        explanation.
    :param check_numerics: Bool. Whether to check numeric issues.
    """

    def __init__(self,
                 logits,
                 n_experiments,
                 group_event_ndims=0,
                 check_numerics=False):
        sign_err_msg = "n_experiments must be positive"
        if isinstance(n_experiments, int):
            if n_experiments <= 0:
                raise ValueError(sign_err_msg)
            self._n_experiments = n_experiments
        else:
            n_experiments = tf.convert_to_tensor(n_experiments, tf.int32)
            _assert_rank_op = tf.assert_rank(
                n_experiments, 0,
                message="n_experiments should be a scalar (0-D Tensor).")
            _assert_positive_op = tf.assert_greater(
                n_experiments, 0, message=sign_err_msg)
            with tf.control_dependencies([_assert_rank_op,
                                          _assert_positive_op]):
                self._n_experiments = tf.identity(n_experiments)

        self._logits = tf.convert_to_tensor(logits, dtype=tf.float32)
        self._check_numerics = check_numerics
        super(Binomial, self).__init__(
            dtype=tf.int32,
            is_continuous=False,
            is_reparameterized=False,
            group_event_ndims=group_event_ndims)

    @property
    def n_experiments(self):
        """The number of experiments."""
        return self._n_experiments

    @property
    def logits(self):
        """The log-odds of probabilities."""
        return self._logits

    def _value_shape(self):
        return tf.constant([], dtype=tf.int32)

    def _get_value_shape(self):
        return tf.TensorShape([])

    def _batch_shape(self):
        return tf.shape(self.logits)

    def _get_batch_shape(self):
        return self.logits.get_shape()

    def _sample(self, n_samples):
        n = self.n_experiments
        if self.logits.get_shape().ndims == 1:
            logits_flat = self.logits
        else:
            logits_flat = tf.reshape(self.logits, [-1])
        log_1_minus_p = -tf.nn.softplus(logits_flat)
        log_p = logits_flat + log_1_minus_p
        stacked_logits_flat = tf.stack([log_1_minus_p, log_p], axis=-1)
        samples_flat = tf.transpose(
            tf.multinomial(stacked_logits_flat, n_samples * n))

        shape = tf.concat([[n, n_samples], self.batch_shape], 0)
        samples = tf.reduce_sum(tf.reshape(samples_flat, shape), axis=0)

        static_n_samples = n_samples if isinstance(n_samples, int) else None
        static_shape = tf.TensorShape([static_n_samples]).concatenate(
            self.get_batch_shape())
        samples.set_shape(static_shape)

        return samples

    def _log_prob(self, given):
        logits = self.logits
        n = tf.to_float(self.n_experiments)
        given = tf.to_float(given)

        log_1_minus_p = -tf.nn.softplus(logits)
        lgamma_n_plus_1 = tf.lgamma(n + 1)
        lgamma_given_plus_1 = tf.lgamma(given + 1)
        lgamma_n_minus_given_plus_1 = tf.lgamma(n - given + 1)

        if self._check_numerics:
            with tf.control_dependencies(
                    [tf.check_numerics(lgamma_given_plus_1,
                                       "lgamma(given + 1)"),
                     tf.check_numerics(lgamma_n_minus_given_plus_1,
                                       "lgamma(n - given + 1)")]):
                lgamma_given_plus_1 = tf.identity(lgamma_given_plus_1)

        return lgamma_n_plus_1 - lgamma_n_minus_given_plus_1 - \
            lgamma_given_plus_1 + given * logits + n * log_1_minus_p

    def _prob(self, given):
        return tf.exp(self._log_prob(given))
