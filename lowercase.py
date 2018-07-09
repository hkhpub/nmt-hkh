wfile = '/hdd/data/iwslt15_en_zh/train_norm.en'
rfile = '/hdd/data/iwslt15_en_zh/train.en'

wf = open(wfile, 'w')
with open(rfile, 'r') as f:
    for line in f.readlines():
        wf.write(line.replace("And ", "").replace("--", "").lower())