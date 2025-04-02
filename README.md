# Create virtual environment
'''python
uv venv --python 3.10 examples/aloha_sim/.venv
source examples/aloha_sim/.venv/bin/activate
uv pip sync examples/aloha_sim/requirements.txt
uv pip install -e packages/openpi-client

uv run scripts/serve_policy.py --env UR3 --default_prompt='press the red button'
'''
#In another terminal run the conda env : 
conda env create -f environment.yml
conda activate openpi_env

cd examples/ur_env
python ur3_infer.py
