"""To perform inference on test set given a trained model."""
from __future__ import print_function

import codecs
import os
import time

import tensorflow as tf

from tensorflow.python.ops import lookup_ops

import attention_model
import model as nmt_model
import model_helper
import utils.iterator_utils as iterator_utils
import utils.misc_utils as utils
import utils.nmt_utils as nmt_utils
import utils.vocab_utils as vocab_utils

__all__ = ["create_infer_model", "load_inference_hparams", "inference"]


def create_infer_model(
    model_creator,
    hparams,
    src_vocab_file,
    tgt_vocab_file,
    scope=None):
  infer_graph = tf.Graph()

  with infer_graph.as_default():
    src_vocab_table = lookup_ops.index_table_from_file(
        src_vocab_file, default_value=vocab_utils.UNK_ID)
    tgt_vocab_table = lookup_ops.index_table_from_file(
        tgt_vocab_file, default_value=vocab_utils.UNK_ID)
    infer_src_placeholder = tf.placeholder(shape=[None], dtype=tf.string)
    infer_src_dataset = tf.contrib.data.Dataset.from_tensor_slices(
        infer_src_placeholder)
    infer_iterator = iterator_utils.get_infer_iterator(
        infer_src_dataset, hparams,
        src_vocab_table, hparams.batch_size,
        src_max_len=hparams.src_max_len)
    infer_model = model_creator(
        hparams,
        iterator=infer_iterator,
        mode=tf.contrib.learn.ModeKeys.INFER,
        source_vocab_table=src_vocab_table,
        target_vocab_table=tgt_vocab_table,
        scope=scope)
  return (infer_graph, infer_model, infer_src_placeholder,
          infer_iterator)


def load_inference_hparams(model_dir, inference_list=None):
  """Load hparams for inference.

  Args:
    model_dir: directory of trained model.
    inference_list: optional, comma-separated list of sentence ids.

  Returns:
    hparams: A tf.HParams() used for inference.
  """
  hparams = utils.load_hparams(model_dir)
  assert hparams

  # Inference indices
  hparams.inference_indices = None
  if inference_list:
    (hparams.inference_indices) = (
        [int(token)  for token in inference_list.split(",")])

  return hparams


def _decode_inference_indices(model, sess, output_infer,
                              output_infer_summary_prefix, hparams):
  """Decoding only a specific set of sentences."""
  inference_indices = hparams.inference_indices
  utils.print_out("  decoding to output %s , num sents %d." %
                  (output_infer, len(inference_indices)))
  start_time = time.time()
  with codecs.getreader("utf-8")(
      tf.gfile.GFile(output_infer, mode="w")) as trans_f:
    trans_f.write("")  # Write empty string to ensure file is created.
    for decode_id in inference_indices:
      nmt_outputs, infer_summary = model.decode(sess)

      # get text translation
      assert nmt_outputs.shape[0] == 1
      translation = nmt_utils.get_translation(nmt_outputs, 0, hparams)

      if infer_summary is not None:  # Attention models
        image_file = output_infer_summary_prefix + str(decode_id) + ".png"
        utils.print_out("  save attention image to %s*" % image_file)
        image_summ = tf.Summary()
        image_summ.ParseFromString(infer_summary)
        with tf.gfile.GFile(image_file, mode="w") as img_f:
          img_f.write(image_summ.value[0].image.encoded_image_string)

      trans_f.write("%s\n" % translation)
      utils.print_out("%s\n" % translation)
  utils.print_time("  done", start_time)


def _load_data(inference_input_file, hparams):
  """Load inference data."""
  with codecs.getreader("utf-8")(tf.gfile.GFile(inference_input_file, mode="r")) as f:
    inference_data = f.read().splitlines()

  if hparams.inference_indices:
    inference_data = [ inference_data[i] for i in hparams.inference_indices ]

  return inference_data


def inference(model_dir,
              inference_input_file,
              inference_output_file,
              hparams,
              num_workers=1,
              jobid=0,
              scope=None):
  if hparams.inference_indices:
    assert num_workers == 1

  if num_workers == 1:
    _single_worker_inference(
        model_dir, inference_input_file, inference_output_file, hparams,
        scope=scope)
  else:
    _multi_worker_inference(
        model_dir, inference_input_file, inference_output_file, hparams,
        num_workers=num_workers, jobid=jobid, scope=scope)


def _single_worker_inference(model_dir,
                             inference_input_file,
                             inference_output_file,
                             hparams,
                             scope=None):
  """Inference with a single worker."""
  output_infer = inference_output_file

  # Read data
  infer_data = _load_data(inference_input_file, hparams)

  assert hparams.vocab_prefix
  src_vocab_file = "%s.%s" % (hparams.vocab_prefix, hparams.src)
  tgt_vocab_file = "%s.%s" % (hparams.vocab_prefix, hparams.tgt)

  if hparams.attention == "":
    model_creator = nmt_model.Model
  else:
    model_creator = attention_model.AttentionModel

  infer_graph, infer_model, infer_src_placeholder, infer_iterator = (
      create_infer_model(model_creator, hparams, src_vocab_file, tgt_vocab_file,
                         scope))
  with tf.Session(graph=infer_graph, config=utils.get_config_proto()) as sess:
    model_helper.create_or_load_model(infer_model, model_dir, sess, hparams)
    sess.run(
        infer_iterator.initializer,
        feed_dict={infer_src_placeholder.name: infer_data})
    # Decode
    utils.print_out("# Start decoding")
    if hparams.inference_indices:
      _decode_inference_indices(infer_model, sess, output_infer, output_infer,
                                hparams)
    else:
      nmt_utils.decode_and_evaluate("infer", infer_model, sess, output_infer,
                                    None, hparams)


def _multi_worker_inference(model_dir,
                            inference_input_file,
                            inference_output_file,
                            hparams,
                            num_workers,
                            jobid,
                            scope=None):
  """Inference using multiple workers."""
  assert num_workers > 1

  final_output_infer = inference_output_file
  output_infer = "%s_%d" % (inference_output_file, jobid)
  output_infer_done = "%s_done_%d" % (inference_output_file, jobid)

  # Read data
  infer_data = _load_data(inference_input_file, hparams)

  # Split data to multiple workers
  total_load = len(infer_data)
  load_per_worker = int((total_load - 1) / num_workers) + 1
  start_position = jobid * load_per_worker
  end_position = min(start_position + load_per_worker, total_load)
  infer_data = infer_data[start_position:end_position]

  assert hparams.vocab_prefix
  src_vocab_file = "%s.%s" % (hparams.vocab_prefix, hparams.src)
  tgt_vocab_file = "%s.%s" % (hparams.vocab_prefix, hparams.tgt)

  if hparams.attention == "":
    model_creator = nmt_model.Model
  else:
    model_creator = attention_model.AttentionModel

  infer_graph, infer_model, infer_src_placeholder, infer_iterator = (
      create_infer_model(model_creator, hparams, src_vocab_file, tgt_vocab_file,
                         scope))

  with tf.Session(graph=infer_graph, config=utils.get_config_proto()) as sess:
    model_helper.create_or_load_model(infer_model, model_dir, sess, hparams)
    sess.run(infer_iterator.initializer,
             {infer_src_placeholder.name: infer_data})
    # Decode
    utils.print_out("# Start decoding")
    worker_sorted_indices = None  # for worker, no worry about sorted indices
    nmt_utils.decode_and_evaluate("infer", infer_model, sess, output_infer,
                                  None, hparams)

    # Change file name to indicate the file writting is completed.
    tf.gfile.Rename(output_infer, output_infer_done, overwrite=True)

    # Job 0 is responsible for the clean up.
    if jobid != 0: return

    # Now write all translations
    with codecs.getreader("utf-8")(
        tf.gfile.GFile(final_output_infer, mode="w")) as final_f:
      for worker_id in range(num_workers):
        worker_infer_done = "%s_done_%d" % (inference_output_file, worker_id)
        while not tf.gfile.Exists(worker_infer_done):
          utils.print_out("  waitting job %d to complete." % worker_id)
          time.sleep(10)

        with codecs.getreader("utf-8")(
            tf.gfile.GFile(worker_infer_done, mode="r")) as f:
          for translation in f:
            final_f.write("%s" % translation)
        tf.gfile.Remove(worker_infer_done)