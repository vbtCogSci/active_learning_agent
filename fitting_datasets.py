import numpy as np
import pickle

from classes.ou_network import OU_Network
from methods.sample_space_methods import build_space
from methods.model_fitting_utilities import fit_models
from methods.states_params_importer import import_states_asdict, import_params_asdict, import_states_params_asdict

## Import behavioural experiment
with open('/mnt/c/Users/vbtes/CompProjects/vbtCogSci/csl_global_analysis/data/global_modelling_data.obj', 'rb') as inFile:
    modelling_data = pickle.load(inFile)

# Choose experiments
experiments = ['experiment_1', 'experiment_2', 'experiment_3']

# Select participans
selected_data = {}
pick_interval = 1
idx = 0
for part, data in modelling_data.items():
    if data['experiment'] in experiments and idx % pick_interval == 0:
        selected_data[part] = data
    
    idx += 1

# Pick states to fit
internal_states_list = ['change_discrete']
action_states_list = ['experience_vao']
sensory_states_list = ['omniscient']
external_state = OU_Network

# Import model dicts
states_dict = import_states_asdict()
params_dict = import_params_asdict()
models_dict = import_states_params_asdict()

# /!\ Data loss warning /!\
reset_summary = False
reset_posteriors = False
# /!\ Data loss warning /!\

# Run fitting function
summary = fit_models(internal_states_list,
                     action_states_list,
                     sensory_states_list,
                     external_state,
                     models_dict,
                     selected_data,
                     reset_summary=reset_summary,
                     reset_posteriors=reset_posteriors)