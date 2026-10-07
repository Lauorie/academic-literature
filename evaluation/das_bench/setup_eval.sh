#!/usr/bin/env bash
# Rebuild the DAS-Eval environment on a GPU host (same pinned versions as the first run).
set -x
D=/root/autodl-tmp/dasbench; cd "$D"
source ~/miniconda3/etc/profile.d/conda.sh
[ -x /root/autodl-tmp/envs/eval/bin/python ] || conda create -y -q -p /root/autodl-tmp/envs/eval -c conda-forge python=3.11
conda activate /root/autodl-tmp/envs/eval
pip install -q --upgrade pip
pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -q "mineru[core]==2.7.6" loguru openai Pillow PyMuPDF tqdm huggingface_hub zstandard
python -c "import torch;print(torch.__version__, torch.cuda.is_available())"
pip show mineru | head -2
python - <<PY
from huggingface_hub import snapshot_download
snapshot_download("opendatalab/PDF-Extract-Kit-1.0", revision="1d9a3cd772329d0f83d84638a789296863f940f9", local_dir="$D/PDF-Extract-Kit-1.0")
print("PEK_DONE")
PY
mkdir -p das2m && cd das2m
for y in 2020 2021 2022 2023 2024 2025 2026; do for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
  f=metadata_${y}-${m}.jsonl.zst; [ -s $f ] && continue
  curl -sSfL -m 900 -o $f.part https://huggingface.co/datasets/ZhikaiXu24/DAS-2M/resolve/main/metadata/$y/$f && mv $f.part $f || rm -f $f.part
done; done
echo "shards $(ls *.zst | wc -l)"
cd "$D" && python tools/das2m_index.py build --shards das2m --db das2m.sqlite
echo SETUP_DONE
