#!/usr/bin/env python3

import sys
from argparse import ArgumentParser
from collections import defaultdict


def parse_args():
  p = ArgumentParser('Constructs vocabulary file.')
  p.add_argument(
      '--input',
      type=str, metavar='FILE', required=True, help='source corpus')
  p.add_argument(
      '--output',
      type=str, metavar='FILE', required=True, help='vocabulary file')
  p.add_argument(
      '--size',
      type=int, metavar='N', required=True, help='vocabulary size')
  args = p.parse_args()
  assert args.size > 3
  return args


def main():
  args = parse_args()

  freq = defaultdict(int)
  num_lines = 0
  with open(args.input) as fp:
    for line in fp:
      num_lines += 1
      for word in line.split():
        freq[word] += 1

  freq_sorted = sorted(freq.items(), key=lambda x: x[1], reverse=True)
  num_unk = sum(x[1] for x in freq_sorted[args.size - 3:])

  with open(args.output, 'w') as fp:
    print('<unk>', file=fp)
    print('<s>', file=fp)
    print('</s>', file=fp)
    for i, (key, val) in zip(range(3, args.size), freq_sorted):
      print('%s' % key, file=fp)

if __name__ == '__main__':
  main()

