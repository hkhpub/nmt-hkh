import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser("calculate percentage of unknown words.")
    parser.add_argument(
        '--vocab_file',
        type=str, metavar='FILE', required=True, help='vocabulary file')
    parser.add_argument(
        '--input_file',
        type=str, metavar='FILE', required=True, help='input file for calculate unknown words')

    args = parser.parse_args()

    vocab_file = open(args.vocab_file, 'r')
    vocabulary = vocab_file.readlines()
    vocabulary = [token.strip() for token in vocabulary]

    input_file = open(args.input_file, 'r')
    tokens = []
    for sent in input_file.readlines():
        tokens += sent.strip().split(" ")

    token_cnt = len(tokens)
    hit_cnt = len([token for token in tokens if token in vocabulary])

    print("hit rate: %.2f %%" % (hit_cnt * 100.0 / token_cnt))