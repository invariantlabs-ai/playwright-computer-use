pip install uv
uv venv
source .venv/bin/activate
uv pip install -U transformers
uv pip install vllm
uv pip install setuptools
TP=1
MODEL_PATH="bytedance-research/UI-TARS-2B-SFT"
uv run python -m vllm.entrypoints.openai.api_server --served-model-name ui-tars  --model ${MODEL_PATH} --limit-mm-per-prompt image=5 -tp ${TP}


# to ssh
ssh ubuntu@?? -L 8000:localhost:8000 -Nt