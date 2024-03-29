import numpy as np
import pickle

from methods.model_fitting_utilities import fit_params_models_partlevel
from methods.states_params_importer import import_states_params_asdict, params_to_fit_importer


## Import behavioural experiment
with open('/mnt/c/Users/vbtes/CompProjects/vbtCogSci/csl_global_analysis/data/global_modelling_data.obj', 'rb') as inFile:
    modelling_data = pickle.load(inFile)



# Select participans
selected_data = {}
pick_interval = 1
idx = 0

# Choose experiments
experiments = ['experiment_1', 'experiment_2', 'experiment_3']

for part, data in modelling_data.items():
    if data['experiment'] in experiments and idx % pick_interval == 0:
        selected_data[part] = data
    idx += 1


models_to_fit = [
    'LC_discrete_attention', # OK, prior OK
    'change_d_obs_fk', # OK, prior OK
    'change_d_obs_cause_effect', # OK
    'change_d_obs_cause', # OK
    'LC_discrete', # OK, prior OK
    'normative', # OK, prior OK
    'ces_strength', # OK
    'ces_no_strength', # OK
    'ces_strength_unrestricted',
    'ces_strength_softmax',
    'ces_no_strength_softmax'
]

# Pick states to fit
internal_states_list = ['change_d_obs_fk']
action_states_list = ['experience_vao']
sensory_states_list = ['omniscient']

fitting_softmax = True
fitting_change = True
fitting_attention = True
# CES
fitting_guess = True
fitting_strength = False
# Prior
fitting_prior = False
random_increment = 1
params_to_fit_tuple = params_to_fit_importer(internal_states_list[0], 
                                             fitting_change=fitting_change,
                                             fitting_attention=fitting_attention,
                                             fitting_guess=fitting_guess,
                                             fitting_strength=fitting_strength,
                                             fitting_prior=fitting_prior,
                                             random_increment=random_increment)
params_initial_guesses = params_to_fit_tuple[0]
params_bounds = params_to_fit_tuple[1]
internal_params_labels = params_to_fit_tuple[2]
action_params_labels = params_to_fit_tuple[3]
sensory_params_labels = params_to_fit_tuple[4]
fitting_list = params_to_fit_tuple[5]

print(f'Fitting: {internal_states_list[0]}...')
print(f'Parameters: {internal_params_labels + action_params_labels + sensory_params_labels}')

# Import model dicts
models_dict = import_states_params_asdict()

# /!\ Data loss warning /!\
reset_summary = False
reset_posteriors = False
# /!\ Data loss warning /!\

# Run fitting function
summary = fit_params_models_partlevel(params_initial_guesses,
                                      params_bounds,
                                      internal_params_labels,
                                      action_params_labels,
                                      sensory_params_labels,
                                      internal_states_list,
                                      action_states_list,
                                      sensory_states_list,
                                      models_dict,
                                      selected_data,
                                      fitting_list)

    
