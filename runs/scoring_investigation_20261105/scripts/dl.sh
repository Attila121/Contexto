#!/bin/bash
cd "$1"
for u in \
 https://huggingface.co/stanfordnlp/glove/resolve/main/glove.6B.zip \
 https://huggingface.co/stanfordnlp/glove/resolve/main/glove.42B.300d.zip \
 https://huggingface.co/stanfordnlp/glove/resolve/main/glove.840B.300d.zip \
 https://huggingface.co/stanfordnlp/glove/resolve/main/glove.twitter.27B.zip \
 https://huggingface.co/LoganKilpatrick/GoogleNews-vectors-negative300/resolve/main/GoogleNews-vectors-negative300.bin.gz \
 https://dl.fbaipublicfiles.com/fasttext/vectors-english/crawl-300d-2M.vec.zip ; do
  f=$(basename "$u"); curl -sL -C - --retry 5 -A "Mozilla/5.0 (research-readonly)" -o "$f.part" "$u" && mv "$f.part" "$f" && echo "OK $f $(date +%T)"
done
echo ALLDONE
