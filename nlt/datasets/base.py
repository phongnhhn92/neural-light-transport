# pylint: disable=relative-beyond-top-level

import tensorflow as tf
tf.compat.v1.enable_eager_execution()

from util import logging as logutil


logger = logutil.Logger(loggee="datasets/base")


class Dataset():
    def __init__(
            self, config, mode, shuffle_buffer_size=64,
            prefetch_buffer_size=None, n_map_parallel_calls=None):
        self._validate_mode(mode)
        self.config = config
        self.mode = mode
        self.shuffle_buffer_size = shuffle_buffer_size
        if prefetch_buffer_size is None:
            prefetch_buffer_size = tf.data.experimental.AUTOTUNE
        self.prefetch_buffer_size = prefetch_buffer_size
        if n_map_parallel_calls is None:
            n_map_parallel_calls = tf.data.experimental.AUTOTUNE
        self.n_map_parallel_calls = n_map_parallel_calls
        self.files = self._glob()
        assert self.files, "No files to process into a dataset"
        self.bs = self._get_batch_size()

    @staticmethod
    def _validate_mode(mode):
        allowed_modes = ('train', 'vali', 'test')
        if mode not in allowed_modes:
            raise ValueError(
                "Invalid mode: {provided}. Allowed modes: {allowed}".format(
                    provided=mode, allowed=allowed_modes))

    def _glob(self):
        """Globs the source data files (like paths to images), each of which
        will be processed by the processing functions below.

        Returns:
            list(str): List of paths to the data files.
        """
        raise NotImplementedError

    def _get_batch_size(self):
        """Useful for NeRF-like models, where the effective batch size may not
        be just number of images, and for models where different modes have
        different batch sizes.

        Returns:
            int: Batch size.
        """
        if 'bs' not in self.config['DEFAULT'].keys():
            raise ValueError((
                "Specify batch size either as 'bs' in the configuration file, "
                "or override this function to generate a value another way"))
        return self.config.getint('DEFAULT', 'bs')

    def _process_example_precache(self, path):
        """Output of this function will be cached.
        """
        raise NotImplementedError

    # pylint: disable=no-self-use
    def _process_example_postcache(self, *args):
        """Move whatever you don't want cached into this function, such as
        processing that involves randomness.

        If you don't override this, this will be a no-op.
        """
        return args

    def build_pipeline(self, filter_predicate=None, seed=None, no_batch=False):
        is_train = self.mode == 'train'
        # Make dataset from files
        files = sorted(self.files)
        dataset = tf.data.Dataset.from_tensor_slices(files)
        # Optional filtering
        if filter_predicate is not None:
            dataset = dataset.filter(filter_predicate)
        # Parallelize processing
        dataset = dataset.map(
            self._process_example_precache,
            num_parallel_calls=self.n_map_parallel_calls)
        cache = self.config.getboolean('DEFAULT', 'cache')
        if cache:
            dataset = dataset.cache()
        # Useful if part of your processing involves randomness
        dataset = dataset.map(
            self._process_example_postcache,
            num_parallel_calls=self.n_map_parallel_calls)
        # Shuffle
        if is_train:
            dataset = dataset.shuffle(self.shuffle_buffer_size, seed=seed)
        # Batching
        if not no_batch:
            # In case you want to make batches yourself
            dataset = dataset.batch(batch_size=self.bs)
        # Prefetching
        datapipe = dataset.prefetch(buffer_size=self.prefetch_buffer_size)
        return datapipe