pip install uv
uv venv
source .venv/bin/activate
uv pip install -U transformers
uv pip install vllm
uv pip install setuptools
TP=4
MODEL_PATH="bytedance-research/UI-TARS-72B-DPO"
uv run python -m vllm.entrypoints.openai.api_server --served-model-name ui-tars  --model ${MODEL_PATH} --limit-mm-per-prompt image=5 -tp ${TP} --max_model_len 16384


# to ssh
ssh ubuntu@?? -L 8000:localhost:8000 -Nt

"--served-model-name ui-tars -tp --download-dir /workspace/models --host 127.0.0.1 --port 18000"