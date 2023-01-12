import numpy as np
import pandas as pd
import pickle
from os.path import exists
from scipy.optimize import minimize
import time
import math
import json

from classes.experiment import Experiment
from classes.agent import Agent
from methods.action_plans import generate_action_plan

from methods.sample_space_methods import build_space_env

# Runs the specified model on the specified data, with given parameters without assuming anything about the structure of data
def generalised_model_fitting(internal_states_list,                # List of internal states names as strings
                              action_states_list,                  # List of action states names as strings
                              sensory_states_list,                 # List of sensory states names as strings
                              models_dict,                         # Dict of model object and parameters: can be changed in separate file                 
                              data_dict,                           # Dict of data for each participants/trial/experiment     
                              fit_or_run='fit',               
                              use_action_plan=False,
                              use_fitted_params=False,             # Flag uses default params if false, else is a dictionary of params            
                              build_space=True,                    # Boolean, set true for pre initialisation of fixed and large objects
                              save_data=True,                      # /!\ Data miss warning /!\ if False does not save the results but simply fit experiments
                              save_full_data=False,                # /!\ Performance warning /!\ if true, stores all posterior distributions over models
                              fit_judgement=False,                 # If true fit judgement
                              verbose=False,                       # If true, log progress on the console
                              file_tag='',
                              file_name='general_summary',
                              K=3,
                              links=np.array([-1, -0.5, 0, 0.5, 1])): 


    # Build internal sample space
    if build_space:
        space_triple = build_space_env(K, links)

    # If save data, generate frames
    if save_data:
        # Define DataFrame
        cols = ['uid', 'participant', 'trial_type', 'trial_name', 'model_name', 'ground_truth', 'posterior_map', 'posterior_judgement', 'prior_judgement', 'prior_entropy', 'posterior_entropy_unsmoothed', 'posterior_entropy', 'model_specs']
        df = pd.DataFrame(columns=cols)
        ## If summary data does not exist, create it
        if not exists(f'./data/general_fitting_outputs/{file_name}_{fit_or_run}{file_tag}.csv'):
            pd.DataFrame(columns=cols).to_csv(f'./data/general_fitting_outputs/{file_name}_{fit_or_run}{file_tag}.csv', index=False)
        else:
            df = pd.read_csv(f'./data/general_fitting_outputs/{file_name}_{fit_or_run}{file_tag}.csv')
            uid_done = df.uid.to_list()

        # Posterior DataFrame
        # One per internal state
        if save_full_data:
            links_cols = [f'link_{i}' for i in range(K**2 - K)] 
            generated_data = {}
            
        
    # Count participant index
    sample_size = len(data_dict.keys())
    done_idx = 0

    for uid, obj_data in data_dict.items():
        print(f'uid {done_idx+1}, out of {sample_size}', )

        # Extract data from participant's trial
        trial_name = obj_data['trial_name'][:-2]
        trial_type = obj_data['trial_type']
        participant = obj_data['pid'] if 'pid' in obj_data.keys() else None
        data = obj_data['data'] # Raw numerical data of variable values
        ground_truth = obj_data['ground_truth'] # Ground truth model from which data has been generated
        inters = obj_data['inters'] # Interventions as is
        judgement_data = obj_data['links_hist'] if 'links_hist' in obj_data.keys() else None # Change in judgement sliders
        posterior_judgement = obj_data['posterior'] if 'posterior' in obj_data.keys() else None # Final states of judgement sliders
        prior_judgement = obj_data['prior'] if 'prior' in obj_data.keys() else None
        
    
        if use_fitted_params:
            fitted_params_dict = use_fitted_params[participant] 
        else:
            fitted_params_dict = None


        # Unpack generic trial relevant parameters
        N = data.shape[0] # Number of datapoints
        K = data.shape[1] # Number of variables

        if isinstance(use_action_plan, float):
            action_plan = generate_action_plan(N, K, time=use_action_plan)
        elif use_action_plan == 'real_actions':
            action_plan = [obj_data['inters'], obj_data['data']]
            acting_len = (1 - np.isnan(action_plan[0])).mean()
        elif use_action_plan in ['actor', 'random', 'obs']:
            action_plan = None
            behaviour = use_action_plan

        # Set up OU netowrk 
        external_state = models_dict['external']['OU_Network']['object'](N, K, 
                                                                         *models_dict['external']['OU_Network']['params']['args'],
                                                                         **models_dict['external']['OU_Network']['params']['kwargs'], 
                                                                         ground_truth=ground_truth)
        if fit_or_run == 'fit':
            external_state.load_trial_data(data) # Load Data

        # Set up states
        ## Internal states and sensory states
        internal_states = []
        sensory_states = []  
        
        for i, model_tags in enumerate(internal_states_list):
            if len(model_tags.split('_&_')) == 2:
                model, tags = model_tags.split('_&_')
            else:
                model = model_tags.split('_&_')[0]

            ## Internal States
            internal_states_kwargs = models_dict['internal'][model]['params']['kwargs'].copy()

            ## Sensory States
            sensory_states_kwargs = models_dict['sensory'][sensory_states_list[i]]['params']['kwargs'].copy()

            # Setup fitted params
            if use_fitted_params and model_tags in fitted_params_dict.keys():
                for param_key, param_val in fitted_params_dict[model_tags].items():
                    # Internal states params
                    if param_key in internal_states_kwargs.keys():
                        internal_states_kwargs[param_key] = param_val

                    # Sensory states params
                    if param_key in sensory_states_kwargs.keys():
                        sensory_states_kwargs[param_key] = param_val

            # Set up internal states
            i_s = models_dict['internal'][model]['object'](N, K, 
                                                           *models_dict['internal'][model]['params']['args'],
                                                           **internal_states_kwargs,
                                                           generate_sample_space = False)

            # Initialse space according to build_space
            i_s.add_sample_space_env(space_triple)

            # Initialise prior distributions for all IS
            i_s.initialise_prior_distribution(prior_judgement)

            # Load data if fitting
            if fit_or_run == 'fit':
                i_s.load_judgement_data(judgement_data, posterior_judgement, fit_judgement)
            
            internal_states.append(i_s)
            
            # Set up sensory states
            sensory_s = models_dict['sensory'][sensory_states_list[i]]['object'](N, K, 
                                                                                 *models_dict['sensory'][sensory_states_list[i]]['params']['args'],
                                                                                 **sensory_states_kwargs)
            sensory_states.append(sensory_s)
    
        ## Action states
        action_states = []
        for model in action_states_list:
            action_states_kwargs = models_dict['actions'][model]['params']['kwargs'].copy()
            if use_fitted_params and model in fitted_params_dict.keys():
                for param_key, param_val in fitted_params_dict[model].items():
                    if param_key in action_states_kwargs.keys():
                        action_states_kwargs[param_key] = param_val
            
            a_s = models_dict['actions'][model]['object'](N, K, 
                                                         *models_dict['actions'][model]['params']['args'],
                                                         **action_states_kwargs)
            # Load action data if fitting
            if fit_or_run == 'fit':
                a_s.load_action_data(inters, data)
            else:
                if action_plan:
                    a_s.load_action_plan(*action_plan)
                else:
                    # If no action plan, behaviour
                    a_s._behaviour = behaviour

            action_states.append(a_s)

        if len(action_states) == 1: # Must be true atm, multiple action states are not supported
            action_states = action_states[0] 
        
        # Create agent
        if len(internal_states) == 1:
            agent = Agent(N, sensory_states[0], internal_states[0], action_states)
        else:
            agent = Agent(N, sensory_states, internal_states, action_states)

        # Create experiment
        experiment = Experiment(agent, external_state)

        # Fit data
        if fit_or_run == 'fit':
            experiment.fit(verbose=verbose)
        else:
            experiment.run(verbose=verbose)

        # If not saving data, continue here
        if not save_data:
            continue

        # Extract relevant data
        ## Populate a dataframe:
        ### Must happens for all internal states in internal states
        ### UID, pid, experiment, difficulty, scenario, model_name, log likelihood, prior_entropy, posterior_entropy, model_specs
        ## Collect posteriors for fitting
        if save_full_data:
            generated_data[uid] = {}

        for i, i_s in enumerate(internal_states):
            
            if save_full_data:
                # Save data
                generated_data[uid][internal_states_list[i]] = {} 
                generated_data[uid][internal_states_list[i]]['pid'] = participant
                generated_data[uid][internal_states_list[i]]['trial_type'] = trial_type
                generated_data[uid][internal_states_list[i]]['trial_name'] = trial_name
                generated_data[uid][internal_states_list[i]]['ground_truth'] = ground_truth
                generated_data[uid][internal_states_list[i]]['posterior_map'] = i_s.MAP
                generated_data[uid][internal_states_list[i]]['posterior_judgement'] = posterior_judgement
                generated_data[uid][internal_states_list[i]]['prior_judgement'] = prior_judgement
                generated_data[uid][internal_states_list[i]]['prior_entropy'] = i_s.prior_entropy
                generated_data[uid][internal_states_list[i]]['posterior_entropy_unsmoothed'] = i_s.posterior_entropy_unsmoothed
                if fitted_params_dict:
                    generated_data[uid][internal_states_list[i]]['fitted_params'] = fitted_params_dict[internal_states_list[i]]
                else:
                    generated_data[uid][internal_states_list[i]]['fitted_params'] = None

                

                # Save df directly
                if 'posteriors_at_judgements' in save_full_data:
                    # Posteriors for each judgement and each trial
                    ## Set up posterior dataframe for each trial and for each model
                    ## Stored in a special folder (TBD...)
                    judge_trial_idx, judge_link_idx = np.where(judgement_data == True)
                    df_posteriors_trial = pd.DataFrame(columns=links_cols, data=space_triple[0])
                    for j, j_idx in enumerate(judge_trial_idx):
                        value = judgement_data[judge_trial_idx, judge_link_idx[j]][0]
                        # Add judgements
                        df_posteriors_trial[f'judgement_{j_idx}'] = df_posteriors_trial[f'link_{judge_link_idx[j]}'] == value
                        # Add posteriors
                        posterior_over_models = np.squeeze(i_s.posterior_over_models_byidx(j_idx))
                        df_posteriors_trial[f'posterior_{j_idx}'] = posterior_over_models

                    generated_data[uid][internal_states_list[i]]['posteriors_at_judgements'] = df_posteriors_trial

                if 'entropy_history' in save_full_data:
                    generated_data[uid][internal_states_list[i]]['entropy_history'] = i_s.entropy_history

                if 'link_entropy_history' in save_full_data:
                    generated_data[uid][internal_states_list[i]]['entropy_history'] = i_s.entropy_history_links

                generated_data[uid][internal_states_list[i]]['interventions'] = inters
                generated_data[uid][internal_states_list[i]]['data'] = data
                generated_data[uid][internal_states_list[i]]['judgement_data'] = judgement_data
            
            ## Generate summary dataframe entry
            if fitted_params_dict:
                fitted_params = fitted_params_dict[internal_states_list[i]]
            else: 
                fitted_params = None
            output = [
                uid,
                participant,
                trial_type,
                trial_name,
                internal_states_list[i], # model name 
                ground_truth, # ground truth model
                i_s.MAP, # Posterior map
                posterior_judgement,
                prior_judgement,
                i_s.prior_entropy, # Prior entropy
                i_s.posterior_entropy_unsmoothed, # Unsmoothed posterior entropy
                i_s.posterior_entropy, # Posterior entropy
                fitted_params # Model specs, for specific parametrisations (None if irrelevant)
            ]
            data_output = {df.columns[i]:[output[i]] for i in range(len(df.columns))}
            out_df = pd.DataFrame(data=data_output)
            df = pd.concat([df, out_df])

        done_idx += 1 

        
        # Save data every 5 participants and reset df
        if save_data and done_idx % 15 == 0:

            if save_full_data:
                with open(f'./data/.models_full_data/full_data_{fit_or_run}{file_tag}.obj', 'wb') as outfile:
                    pickle.dump(generated_data, outfile)

            df_old = pd.read_csv(f'./data/general_fitting_outputs/{file_name}_{fit_or_run}{file_tag}.csv')
            pd.concat([df_old, df], ignore_index=True).to_csv(f'./data/general_fitting_outputs/{file_name}_{fit_or_run}{file_tag}.csv', index=False)
            # Resets dfs
            df_old = None
            df = pd.DataFrame(columns=cols)

    
    # Final save
    if save_data:

        if save_full_data:
            with open(f'./data/.models_full_data/{file_name}_{fit_or_run}{file_tag}.obj', 'wb') as outfile:
                pickle.dump(generated_data, outfile)

        df_old = pd.read_csv(f'./data/general_fitting_outputs/{file_name}_{fit_or_run}{file_tag}.csv')
        pd.concat([df_old, df], ignore_index=True).to_csv(f'./data/general_fitting_outputs/{file_name}_{fit_or_run}{file_tag}.csv', index=False)
            
        return pd.read_csv(f'./data/general_fitting_outputs/{file_name}_{fit_or_run}{file_tag}.csv')



        

# Fit models to data, independent of participant's judgement
## No smoothing nor temperature parameter

# Returns: None
# Saves to file
## df: a DataFrame of summary statistics
## posteriors: a Dataframe of posteriors for all trials
## 1 file per model
### full distribution over models
##### => Can be represented by df, easy to compute marginals: cols = [link1, link2, ..., link6, p(m)_utid_1, p(m)_utid_2, ..., p(m)_utid_1200]

## posterior history: a collection of matrices representing posterior distributions throughout the trial
### full distribution over models 
##### => Can be represented by df, easy to compute marginals: cols = [link1, link2, ..., link6, p(m)_0, p(m)_1, ..., p(m)_N]
### marginal over links

## General wrapper for fit_participant

def fit_models(internal_states_list,                # List of internal states names as strings
               action_states_list,                  # List of action states names as strings
               sensory_states_list,                 # List of sensory states names as strings
               models_dict,                         # Dict of model object and parameters: can be changed in separate file                 
               data_dict,                           # Dict of data for each participants/trial/experiment     
               fit_or_run='fit',               
               use_action_plan=False,
               use_fitted_params=False,             # Flag uses default params if false, else is a dictionary of params            
               build_space=True,                    # Boolean, set true for pre initialisation of fixed and large objects
               save_data=True,                      # /!\ Data miss warning /!\ if False does not save the results but simply fit experiments
               save_full_data=False,                # /!\ Performance warning /!\ if true, stores all posterior distributions over models
               fit_judgement=False,                 # If true fit judgement
               verbose=False,                       # If true, log progress on the console
               file_tag=''):                             

    # General loop
    ## Initialise general invariant parameters
    K = 3
    links = np.array([-1, -0.5, 0, 0.5, 1]) # Possible link values


    # Build internal sample space
    if build_space:
        space_triple = build_space_env(K, links)

    # If save data, generate frames
    if save_data:
        # Define DataFrame
        cols = ['utid', 'pid', 'experiment', 'difficulty', 'scenario', 'model_name', 'ground_truth', 'posterior_map', 'posterior_judgement', 'prior_judgement', 'prior_entropy', 'posterior_entropy_unsmoothed', 'posterior_entropy', 'model_specs']
        df = pd.DataFrame(columns=cols)
        ## If summary data does not exist, create it
        if not exists(f'./data/model_fitting_outputs/summary_data_{fit_or_run}{file_tag}.csv'):
            pd.DataFrame(columns=cols).to_csv(f'./data/model_fitting_outputs/summary_data_{fit_or_run}{file_tag}.csv', index=False)
            utid_done = []
        else:
            df = pd.read_csv(f'./data/model_fitting_outputs/summary_data_{fit_or_run}{file_tag}.csv')
            utid_done = df.utid.to_list()

        # Posterior DataFrame
        # One per internal state
        if save_full_data:
            links_cols = [f'link_{i}' for i in range(K**2 - K)] 
            generated_data = {}
            
        
    # Count participant index
    sample_size = len(data_dict.keys())
    part_idx = 0

    for participant, part_data in data_dict.items():
        print(f'participant {part_idx+1}, out of {sample_size}', )

        # Participant metadata
        part_experiment = part_data['experiment']
        trials = part_data['trials']

        if use_fitted_params:
            fitted_params_dict = use_fitted_params[participant] 

        for trial_type, trial_data in trials.items():
            
            # Extract data from participant's trial
            model_name = trial_data['name'][:-2]
            difficulty = trial_type
            data = trial_data['data'] # Raw numerical data of variable values
            ground_truth = trial_data['ground_truth'] # Ground truth model from which data has been generated
            inters = trial_data['inters'] # Interventions as is
            inters_fit = trial_data['inters_fit'] # Interventions with removed movements
            judgement_data = trial_data['links_hist'] # Change in judgement sliders
            posterior_judgement = trial_data['posterior'] # Final states of judgement sliders
            prior_judgement = trial_data['prior'] if 'prior' in trial_data.keys() else None
            utid = trial_data['utid']

            if utid in utid_done:
                print('utid done.')
                continue
            # Unpack generic trial relevant parameters
            N = data.shape[0] # Number of datapoints
            K = data.shape[1] # Number of variables

            if isinstance(use_action_plan, float):
                action_plan = generate_action_plan(N, K, time=use_action_plan)
            elif use_action_plan == 'real_actions':
                action_plan = [trial_data['inters'], trial_data['data']]
                acting_len = (1 - np.isnan(action_plan[0])).mean()
            elif use_action_plan in ['actor', 'random', 'obs']:
                action_plan = None
                behaviour = use_action_plan

            # Set up OU netowrk 
            external_state = models_dict['external']['OU_Network']['object'](N, K, 
                                                                             *models_dict['external']['OU_Network']['params']['args'],
                                                                             **models_dict['external']['OU_Network']['params']['kwargs'], 
                                                                             ground_truth=ground_truth)
            if fit_or_run == 'fit':
                external_state.load_trial_data(data) # Load Data

            # Set up states
            ## Internal states and sensory states
            internal_states = []
            sensory_states = []  

            for i, model_tags in enumerate(internal_states_list):

                if len(model_tags.split('_&_')) == 2:
                    model, tags = model_tags.split('_&_')
                else:
                    model = model_tags.split('_&_')[0]

                ## Internal States
                internal_states_kwargs = models_dict['internal'][model]['params']['kwargs'].copy()
                ## Sensory States
                sensory_states_kwargs = models_dict['sensory'][sensory_states_list[i]]['params']['kwargs'].copy()

                # Setup fitted params
                if use_fitted_params and model_tags in fitted_params_dict.keys():
                    for param_key, param_val in fitted_params_dict[model_tags].items():
                        # Internal states params
                        if param_key in internal_states_kwargs.keys():
                            internal_states_kwargs[param_key] = param_val
                        # Sensory states params
                        if param_key in sensory_states_kwargs.keys():
                            sensory_states_kwargs[param_key] = param_val


                # Set up internal states
                i_s = models_dict['internal'][model]['object'](N, K, 
                                                               *models_dict['internal'][model]['params']['args'],
                                                               **internal_states_kwargs,
                                                               generate_sample_space = False)
                # Initialse space according to build_space
                i_s.add_sample_space_env(space_triple)
                # Initialise prior distributions for all IS
                i_s.initialise_prior_distribution(prior_judgement)
                # Load data if fitting
                if fit_or_run == 'fit':
                    i_s.load_judgement_data(judgement_data, posterior_judgement, fit_judgement)
                
                internal_states.append(i_s)
                
                # Set up sensory states
                sensory_s = models_dict['sensory'][sensory_states_list[i]]['object'](N, K, 
                                                                                     *models_dict['sensory'][sensory_states_list[i]]['params']['args'],
                                                                                     **sensory_states_kwargs)
                sensory_states.append(sensory_s)
     

            ## Action states
            action_states = []
            for model in action_states_list:
                action_states_kwargs = models_dict['actions'][model]['params']['kwargs'].copy()
                if use_fitted_params and model in fitted_params_dict.keys():
                    for param_key, param_val in fitted_params_dict[model].items():
                        if param_key in action_states_kwargs.keys():
                            action_states_kwargs[param_key] = param_val
                
                a_s = models_dict['actions'][model]['object'](N, K, 
                                                             *models_dict['actions'][model]['params']['args'],
                                                             **action_states_kwargs)
                # Load action data if fitting
                if fit_or_run == 'fit':
                    a_s.load_action_data(inters, data, inters_fit)
                else:
                    if action_plan:
                        a_s.load_action_plan(*action_plan)
                    else:
                        # If no action plan, behaviour
                        a_s._behaviour = behaviour
    
                action_states.append(a_s)

            if len(action_states) == 1: # Must be true atm, multiple action states are not supported
                action_states = action_states[0] 

            
            # Create agent
            if len(internal_states) == 1:
                agent = Agent(N, sensory_states[0], internal_states[0], action_states)
            else:
                agent = Agent(N, sensory_states, internal_states, action_states)

            # Create experiment
            experiment = Experiment(agent, external_state)

            # Fit data
            if fit_or_run == 'fit':
                experiment.fit(verbose=verbose)
            else:
                experiment.run(verbose=verbose)


            # If not saving data, continue here
            if not save_data:
                continue

            # Extract relevant data
            ## Populate a dataframe:
            ### Must happens for all internal states in internal states
            ### UID, pid, experiment, difficulty, scenario, model_name, log likelihood, prior_entropy, posterior_entropy, model_specs
            ## Collect posteriors for fitting
            if save_full_data:
                generated_data[utid] = {}
            for i, i_s in enumerate(internal_states):
                
                if save_full_data:
                    # Save data
                    generated_data[utid][internal_states_list[i]] = {} 

                    generated_data[utid][internal_states_list[i]]['pid'] = participant
                    generated_data[utid][internal_states_list[i]]['experiment'] = part_experiment
                    generated_data[utid][internal_states_list[i]]['difficulty'] = difficulty
                    generated_data[utid][internal_states_list[i]]['scenario'] = model_name
                    generated_data[utid][internal_states_list[i]]['ground_truth'] = ground_truth
                    generated_data[utid][internal_states_list[i]]['posterior_map'] = i_s.MAP
                    generated_data[utid][internal_states_list[i]]['posterior_judgement'] = posterior_judgement
                    generated_data[utid][internal_states_list[i]]['prior_judgement'] = prior_judgement
                    generated_data[utid][internal_states_list[i]]['prior_entropy'] = i_s.prior_entropy
                    generated_data[utid][internal_states_list[i]]['posterior_entropy_unsmoothed'] = i_s.posterior_entropy_unsmoothed
                    generated_data[utid][internal_states_list[i]]['fitted_params'] = fitted_params_dict[internal_states_list[i]]

                    # Posteriors for each judgement and each trial
                    ## Set up posterior dataframe for each trial and for each model
                    ## Stored in a special folder (TBD...)
                    judge_trial_idx, judge_link_idx = np.where(judgement_data == True)
                    df_posteriors_trial = pd.DataFrame(columns=links_cols, data=space_triple[0])

                    for j, j_idx in enumerate(judge_trial_idx):
                        value = judgement_data[judge_trial_idx, judge_link_idx[j]][0]
                        # Add judgements
                        df_posteriors_trial[f'judgement_{j_idx}'] = df_posteriors_trial[f'link_{judge_link_idx[j]}'] == value
                        # Add posteriors
                        posterior_over_models = np.squeeze(i_s.posterior_over_models_byidx(j_idx))
                        df_posteriors_trial[f'posterior_{j_idx}'] = posterior_over_models

                    # Save df directly
                    if 'posteriors_at_judgements' in save_full_data:
                        generated_data[utid][internal_states_list[i]]['posteriors_at_judgements'] = df_posteriors_trial
                    if 'entropy_history' in save_full_data:
                        generated_data[utid][internal_states_list[i]]['entropy_history'] = i_s.entropy_history
                    if 'link_entropy_history' in save_full_data:
                        generated_data[utid][internal_states_list[i]]['entropy_history'] = i_s.entropy_history_links
                    generated_data[utid][internal_states_list[i]]['interventions'] = inters
                    generated_data[utid][internal_states_list[i]]['data'] = data
                    generated_data[utid][internal_states_list[i]]['judgement_data'] = judgement_data
                
                ## Generate summary dataframe entry
                
                output = [
                    utid,
                    participant,
                    part_experiment,
                    difficulty,
                    model_name,
                    internal_states_list[i], # model name 
                    ground_truth, # ground truth model
                    i_s.MAP, # Posterior map
                    posterior_judgement,
                    prior_judgement,
                    i_s.prior_entropy, # Prior entropy
                    i_s.posterior_entropy_unsmoothed, # Unsmoothed posterior entropy
                    i_s.posterior_entropy, # Posterior entropy
                    None
                ]
                if use_fitted_params:
                    output[-1] = fitted_params_dict[internal_states_list[i]] # Model specs, for specific parametrisations (None if irrelevant)

                data_output = {df.columns[i]:[output[i]] for i in range(len(df.columns))}
                out_df = pd.DataFrame(data=data_output)

                df = pd.concat([df, out_df])


        part_idx += 1 

        
        # Save data every 5 participants and reset df
        if save_data and part_idx % 15 == 0:
            print('Saving...')

            if save_full_data:
                with open(f'./data/.models_full_data/full_data_{fit_or_run}{file_tag}.obj', 'wb') as outfile:
                    pickle.dump(generated_data, outfile)

            df_old = pd.read_csv(f'./data/model_fitting_outputs/summary_data_{fit_or_run}{file_tag}.csv')
            pd.concat([df_old, df], ignore_index=True).to_csv(f'./data/model_fitting_outputs/summary_data_{fit_or_run}{file_tag}.csv', index=False)
            # Resets dfs
            df_old = None
            df = pd.DataFrame(columns=cols)
            print('Done.')

    
    # Final save
    if save_data:

        if save_full_data:
            with open(f'./data/.models_full_data/full_data_{fit_or_run}{file_tag}.obj', 'wb') as outfile:
                pickle.dump(generated_data, outfile)

        df_old = pd.read_csv(f'./data/model_fitting_outputs/summary_data_{fit_or_run}{file_tag}.csv')
        pd.concat([df_old, df], ignore_index=True).to_csv(f'./data/model_fitting_outputs/summary_data_{fit_or_run}{file_tag}.csv', index=False)
            
        return pd.read_csv(f'./data/model_fitting_outputs/summary_data_{fit_or_run}{file_tag}.csv')



# Recover final judgements
# These need to be recovered as a dataframe with links in the 6 first columns and then the index of the model for each columns
def extract_final_judgements(data_dict):      # Dict of data for each participants/trial/experiment

    # General loop
    ## Initialise general invariant parameters
    K = 3
    links = np.array([-1, -0.5, 0, 0.5, 1]) # Possible link values

    # Build internal sample space
    space_triple = build_space_env(K, links)
        
    # Count participant index
    sample_size = len(data_dict.keys())
    part_idx = 0

    # Posterior DataFrame
    # One per internal state
    links_cols = [f'link_{i}' for i in range(K**2 - K)]
    # Create files if they don't exist yet
    if not exists(f'./data/model_fitting_outputs/final_judgements.csv'):
        df_links = pd.DataFrame(columns=links_cols, data=space_triple[0])
        df_links.to_csv(f'./data/model_fitting_outputs/final_judgements.csv', index=False)
    else:
        df_links = pd.read_csv(f'./data/model_fitting_outputs/final_judgements.csv')

    # Stores index and initialise empty dataframe of posteriors
    posterior_index = df_links.index
    df = pd.DataFrame(index=posterior_index)
    

    for participant, part_data in data_dict.items():
        print(f'participant {part_idx+1}, out of {sample_size}', )

        # Participant metadata
        part_experiment = part_data['experiment']
        trials = part_data['trials']

        for trial_type, trial_data in trials.items():
            
            # Extract data from participant's trial
            model_name = trial_data['name'][:-2]
            difficulty = trial_type
            data = trial_data['data'] # Raw numerical data of variable values
            ground_truth = trial_data['ground_truth'] # Ground truth model from which data has been generated
            inters = trial_data['inters'] # Interventions as is
            inters_fit = trial_data['inters_fit'] # Interventions with removed movements
            judgement_data = trial_data['links_hist'] # Change in judgement sliders
            posterior_judgement = trial_data['posterior'] # Final states of judgement sliders
            prior_judgement = trial_data['prior'] if 'prior' in trial_data.keys() else None
            utid = trial_data['utid']
            #utid = f'{part_experiment[-1]}_{participant}_{model_name}_{difficulty}'

            final_judgement = (space_triple[0] == posterior_judgement).all(axis=1)

            # Posterior for each model
            df[utid] = final_judgement

            # Every 5 participants, save data and reset dfs_posteriors
            if part_idx % 30 == 0:
                df_old = pd.read_csv(f'./data/model_fitting_outputs/final_judgements.csv')
                pd.concat([df_old, df], axis=1).to_csv(f'./data/model_fitting_outputs/final_judgements.csv', index=False)
                # Reset dfs
                df_old = None  
                df = pd.DataFrame(index=posterior_index)


        if part_idx == sample_size - 1:
            df_old = pd.read_csv(f'./data/model_fitting_outputs/final_judgements.csv')
            pd.concat([df_old, df], axis=1).to_csv(f'./data/model_fitting_outputs/final_judgements.csv', index=False)

        part_idx += 1



## Softmax temperature log likelihood
def softmax_neg_log_likelihood(temp, dataset, selection, return_selection=False):
    softmax_unnorm = np.exp(dataset * temp)
    softmax = softmax_unnorm / softmax_unnorm.sum(axis=0).reshape((1, dataset.shape[1]))

    judgements_likelihood = softmax[selection]

    log_likelihood = np.log(judgements_likelihood)
    
    if return_selection:
        return - log_likelihood
    else:
        return - log_likelihood.sum()




## General wrapper for fit_participant
def fit_params_models_partlevel(params_initial_guesses,              # Initial guesses for params to fit
                                params_bounds,                       # Bounds of params
                                internal_params_labels,              # List of labels and indices in params of to fit of internal states params
                                action_params_labels,                # List of labels and indices in params of to fit of action states params
                                sensory_params_labels,               # List of labels and indices in params of to fit of action states params
                                internal_states_list,                # List of internal states names as strings
                                action_states_list,                  # List of action states names as strings
                                sensory_states_list,                 # List of sensory states names as strings
                                models_dict,                         # Dict of model object and parameters: can be changed in separate file                 
                                data_dict,
                                fitting_list,                           # Dict of data for each participants/trial/experiment
                                build_space=True,                    # Boolean, set true for pre initialisation of fixed and large objects
                                save_data=True,                       # /!\ Data miss warning /!\ if False does not save the results but simply fit experiments
                                outfile_path=None):                     
    
    
    # General loop
    ## Initialise general invariant parameters

    # Build internal sample space
    if build_space:
        space_triple = build_space_env()

    # Define outfile_path
    if not outfile_path:
        out_file = f'./data/params_fitting_outputs/{internal_states_list[0]}/summary_fit_{"_".join(fitting_list)}.csv'
    else:
        out_file = outfile_path

    # If save data, generate frames
    if save_data:
        if exists(out_file):
            df = pd.read_csv(out_file)
            if 'Unnamed: 0' in df.columns:
                df = df.drop(['Unnamed: 0'], axis=1)
            if not df.empty:
                pids_done = df.pid.to_list()
            else:
                pids_done = []
        else:
            # Define DataFrame
            cols = ['pid', 'experiment', 'num_trials', 'model_name', 'nLL', 'bic', 'params', 'params_labels', 'success', 'message', 'time']
            df = pd.DataFrame(columns=cols)
            pids_done = []
            df.to_csv(out_file, index=False)
        


        
    # Count participant index
    sample_size = len(data_dict.keys())
    part_idx = 0
    start = time.perf_counter()
    for participant, part_data in data_dict.items():
        tic = time.perf_counter()
        print(f'participant {part_idx+1}, out of {sample_size}. Elapsed = {(tic - start)/60} minutes' )

        if participant in pids_done:
            print(f'Participant {participant} done, passing...')
            part_idx += 1
            continue
        # Participant metadata
        part_experiment = part_data['experiment']

        x_in = params_initial_guesses
        params_fixed = (
            part_data,
            internal_states_list,
            action_states_list,                  # List of action states names as strings
            sensory_states_list,                 # List of sensory states names as stringsmodels_dict, 
            models_dict,
            internal_params_labels,              # List of labels and indices in params of to fit of internal states params
            action_params_labels,
            sensory_params_labels,
            space_triple 
        )

        minimize_out = minimize(fit_participant, 
                                x_in, 
                                method='Powell', 
                                options={'xtol':1e-3, 'ftol':1e-3}, 
                                args=params_fixed, 
                                bounds=params_bounds)

        # Extract relevant data

        # If not saving data, continue here
        if not save_data:
            part_idx += 1 
            continue
            
        toc = time.perf_counter()

        if 'prior_param' in fitting_list:
            num_labels = len([name for name in part_data['trials'].keys() if name in ['label', 'congruent', 'incongruent', 'implausible']])
            num_generic = len([name for name in part_data['trials'].keys() if name not in ['label', 'congruent', 'incongruent', 'implausible']])
            num_trials = len(part_data['trials'].keys())
            penalty = num_labels * len(minimize_out.x) / num_trials + num_generic * (len(minimize_out.x) - 1) / num_trials
            bic = penalty * np.log(len(part_data['trials'].keys())) + 2 * minimize_out.fun
        else:
            bic = len(minimize_out.x) * np.log(len(part_data['trials'].keys())) + 2 * minimize_out.fun
        
        out_data = [
            participant,
            part_experiment,
            len(part_data['trials'].keys()),
            internal_states_list[0],
            minimize_out.fun,
            bic,
            minimize_out.x,
            internal_params_labels + action_params_labels + sensory_params_labels,  
            minimize_out.success,
            minimize_out.message,
            (toc - tic) / 60
        ]

        print(minimize_out.x)
        print(minimize_out.fun)

        df.loc[len(df.index)] = out_data
        # Save data every 5 participants and reset df
        if part_idx % 15 == 0:
            print('Saving...')
            df.to_csv(out_file, index=False)

        part_idx += 1 

    
    # Final save
    if save_data:
        df.to_csv(out_file, index=False)    
        return df


## Fit participant wise with run
def fit_participant(params_to_fit, 
                    part_data, 
                    internal_states_list,                # List of internal states names as strings
                    action_states_list,                  # List of action states names as strings
                    sensory_states_list,                 # List of sensory states names as stringsmodels_dict, 
                    models_dict,
                    internal_params_labels,              # List of labels and indices in params of to fit of internal states params
                    action_params_labels,
                    sensory_params_labels,
                    space_triple,
                    fit_judgement=False):                 

    trials = part_data['trials']
    nLL = 0

    for trial_type, trial_data in trials.items():
        
        # Extract data from participant's trial
        model_name = trial_data['name'][:-2]
        difficulty = trial_type
        data = trial_data['data'] # Raw numerical data of variable values
        ground_truth = trial_data['ground_truth'] # Ground truth model from which data has been generated
        inters = trial_data['inters'] # Interventions as is
        inters_fit = trial_data['inters_fit'] # Interventions with removed movements
        judgement_data = trial_data['links_hist'] # Change in judgement sliders
        posterior_judgement = trial_data['posterior'] # Final states of judgement sliders
        prior_judgement = trial_data['prior'] if 'prior' in trial_data.keys() else None
        utid = trial_data['utid']

        # Unpack generic trial relevant parameters
        N = data.shape[0] # Number of datapoints
        K = data.shape[1] # Number of variables

        # Set up OU netowrk 
        external_state = models_dict['external']['OU_Network']['object'](N, K, 
                                                                           *models_dict['external']['OU_Network']['params']['args'],
                                                                           **models_dict['external']['OU_Network']['params']['kwargs'], 
                                                                           ground_truth=ground_truth)
        external_state.load_trial_data(data) # Load Data

        # Set up states
        ## Internal states
        internal_states = []   
        
        for model in internal_states_list:
            internal_states_kwargs = models_dict['internal'][model]['params']['kwargs']
            if internal_params_labels:
                for i, param_fit in enumerate(internal_params_labels):
                    internal_states_kwargs[param_fit[0]] = params_to_fit[param_fit[1]]

            i_s = models_dict['internal'][model]['object'](N, K, 
                                                           *models_dict['internal'][model]['params']['args'],
                                                           **internal_states_kwargs,
                                                           generate_sample_space = False)
            # Initialse space according to build_space
            i_s.add_sample_space_env(space_triple)
            # Initialise prior distributions for all IS
            i_s.initialise_prior_distribution(prior_judgement)
            # Load data

            ###### TWO CHOICES HERE, EITHER SOFTMAX THROUGH THE TRIAL (OR AT THE END)
            i_s.load_judgement_data(judgement_data, posterior_judgement, fit_judgement)
            internal_states.append(i_s)

        ## Action states
        action_states = []
        for model in action_states_list:
            action_states_kwargs = models_dict['actions'][model]['params']['kwargs']
            if action_params_labels:
                for i, param_fit in enumerate(action_params_labels):
                    action_states_kwargs[param_fit[0]] = params_to_fit[param_fit[1]]

            a_s = models_dict['actions'][model]['object'](N, K, 
                                                         *models_dict['actions'][model]['params']['args'],
                                                         **action_states_kwargs)
            # Load action data
            a_s.load_action_data(inters, data, inters_fit)
            action_states.append(a_s)
        if len(action_states) == 1: # Must be true atm, multiple action states are not supported
            action_states = action_states[0] 

        ## Sensory states
        sensory_states = []
        for model in sensory_states_list:
            sensory_states_kwargs = models_dict['sensory'][model]['params']['kwargs']
            if sensory_params_labels:
                for i, param_fit in enumerate(sensory_params_labels):
                    sensory_states_kwargs[param_fit[0]] = params_to_fit[param_fit[1]]
            sensory_s = models_dict['sensory'][model]['object'](N, K, 
                                                                *models_dict['sensory'][model]['params']['args'],
                                                                **sensory_states_kwargs)
            sensory_states.append(sensory_s)
        
        if len(sensory_states) == 1: # Must be true atm, multiple sensory states are not supported
            sensory_states = sensory_states[0]

        # Create agent
        if len(internal_states) == 1:
            agent = Agent(N, sensory_states, internal_states[0], action_states)
        else:
            agent = Agent(N, sensory_states, internal_states, action_states)

        # Create experiment
        experiment = Experiment(agent, external_state)

        # Fit data
        experiment.fit(console=False)

        # Extract relevant data
        # Extract posterior
        judgement_LL = -1 * internal_states[0].posterior_PF(posterior_judgement, log=True)[0]
        if not math.isnan(judgement_LL):
            nLL += judgement_LL

    return nLL




## General wrapper for fit_participant
def fit_params_models_grouplevel(params_initial_guesses,              # Initial guesses for params to fit
                                 params_bounds,                       # Bounds of params
                                 internal_params_labels,              # List of labels and indices in params of to fit of internal states params
                                 action_params_labels,                # List of labels and indices in params of to fit of action states params
                                 sensory_params_labels,               # List of labels and indices in params of to fit of action states params
                                 internal_states_list,                # List of internal states names as strings
                                 action_states_list,                  # List of action states names as strings
                                 sensory_states_list,                 # List of sensory states names as strings
                                 models_dict,                         # Dict of model object and parameters: can be changed in separate file                 
                                 data_dict,
                                 fitting_list,                        # Dict of data for each participants/trial/experiment
                                 experiment,
                                 build_space=True,                    # Boolean, set true for pre initialisation of fixed and large objects
                                 save_data=True,
                                 outfile_path=None):                     # /!\ Data miss warning /!\ if False does not save the results but simply fit experiments
    # General loop
    ## Initialise general invariant parameters

    # Define outfile_path
    if not outfile_path:
        out_file = f'./data/group_params_fitting_outputs/{internal_states_list[0]}/summary_fit_{"_".join(fitting_list)}.csv'
    else:
        out_file = outfile_path


    # Build internal sample space
    if build_space:
        space_triple = build_space_env()

    # If save data, generate frames
    if save_data:
        if exists(out_file):
            df = pd.read_csv(out_file)
            if 'Unnamed: 0' in df.columns:
                df = df.drop(['Unnamed: 0'], axis=1)
        else:
            # Define DataFrame
            cols = ['pid', 'experiment', 'num_trials', 'model_name', 'nLL', 'bic', 'params', 'params_labels', 'success', 'message', 'time']
            df = pd.DataFrame(columns=cols)

        if exists(out_file):
            df = pd.read_csv(out_file)
            if 'Unnamed: 0' in df.columns:
                df = df.drop(['Unnamed: 0'], axis=1)
            if not df.empty:
                experiment_done = df.loc[df.index[0], 'experiment']
                if experiment_done == experiment:
                    print(f'{experiment} already done. Passing...')
                    return

        else:
            # Define DataFrame
            cols = ['pid', 'experiment', 'num_trials', 'model_name', 'nLL', 'bic', 'params', 'params_labels', 'success', 'message', 'time']
            df = pd.DataFrame(columns=cols)
            pids_done = []
            df.to_csv(out_file, index=False)

        

        
    # Count participant index
    sample_size = len(data_dict.keys())
    part_idx = 0

    tic = time.perf_counter()

    x_in = params_initial_guesses
    params_fixed = (
        data_dict,
        internal_states_list,
        action_states_list,                  # List of action states names as strings
        sensory_states_list,                 # List of sensory states names as stringsmodels_dict, 
        models_dict,
        internal_params_labels,              # List of labels and indices in params of to fit of internal states params
        action_params_labels,
        sensory_params_labels,
        space_triple 
    )
    minimize_out = minimize(fit_group, 
                            x_in, 
                            method='Powell', 
                            options={'ftol':1e-2}, 
                            args=params_fixed, 
                            bounds=params_bounds)
    # Extract relevant data
    # If not saving data, continue here
        
    toc = time.perf_counter()
    if 'prior_param' in fitting_list:
        # Compute true BIC
        bic = len(minimize_out.x) * np.log(sample_size) + 2 * minimize_out.fun
    else:
        bic = len(minimize_out.x) * np.log(sample_size) + 2 * minimize_out.fun
    

    out_data = [
        np.nan,
        experiment,
        np.nan,
        internal_states_list[0],
        minimize_out.fun,
        bic,
        minimize_out.x,
        internal_params_labels + action_params_labels + sensory_params_labels,  
        minimize_out.success,
        minimize_out.message,
        (toc - tic) / 60
    ]

    
    df.loc[len(df.index)] = out_data
    
    
    # Final save
    if save_data:
        df.to_csv(out_file, index=False)    
        return df



## Fit participant wise with run
def fit_group(params_to_fit, 
              data_dict, 
              internal_states_list,                # List of internal states names as strings
              action_states_list,                  # List of action states names as strings
              sensory_states_list,                 # List of sensory states names as stringsmodels_dict, 
              models_dict,
              internal_params_labels,              # List of labels and indices in params of to fit of internal states params
              action_params_labels,
              sensory_params_labels,
              space_triple,
              fit_judgement=False):                 

    nLL = 0
    num_done = 0
    num_trials = 0
    print(params_to_fit)
    for participant, part_data in data_dict.items():

        trials = part_data['trials']
        
        part_nLL = 0

        for trial_type, trial_data in trials.items():

            # Extract data from participant's trial
            model_name = trial_data['name'][:-2]
            difficulty = trial_type
            data = trial_data['data'] # Raw numerical data of variable values
            ground_truth = trial_data['ground_truth'] # Ground truth model from which data has been generated
            inters = trial_data['inters'] # Interventions as is
            inters_fit = trial_data['inters_fit'] # Interventions with removed movements
            judgement_data = trial_data['links_hist'] # Change in judgement sliders
            posterior_judgement = trial_data['posterior'] # Final states of judgement sliders
            prior_judgement = trial_data['prior'] if 'prior' in trial_data.keys() else None
            utid = trial_data['utid']

            # Unpack generic trial relevant parameters
            N = data.shape[0] # Number of datapoints
            K = data.shape[1] # Number of variables

            # Set up OU netowrk 
            external_state = models_dict['external']['OU_Network']['object'](N, K, 
                                                                               *models_dict['external']['OU_Network']['params']['args'],
                                                                               **models_dict['external']['OU_Network']['params']['kwargs'], 
                                                                               ground_truth=ground_truth)
            external_state.load_trial_data(data) # Load Data

            # Set up states
            ## Internal states
            internal_states = []   

            for model in internal_states_list:
                internal_states_kwargs = models_dict['internal'][model]['params']['kwargs']
                if internal_params_labels:
                    for i, param_fit in enumerate(internal_params_labels):
                        internal_states_kwargs[param_fit[0]] = params_to_fit[param_fit[1]]

                i_s = models_dict['internal'][model]['object'](N, K, 
                                                               *models_dict['internal'][model]['params']['args'],
                                                               **internal_states_kwargs,
                                                               generate_sample_space = False)
                # Initialse space according to build_space
                i_s.add_sample_space_env(space_triple)
                # Initialise prior distributions for all IS
                i_s.initialise_prior_distribution(prior_judgement)
                # Load data

                ###### TWO CHOICES HERE, EITHER SOFTMAX THROUGH THE TRIAL (OR AT THE END)
                i_s.load_judgement_data(judgement_data, posterior_judgement, fit_judgement)
                internal_states.append(i_s)

            ## Action states
            action_states = []
            for model in action_states_list:
                action_states_kwargs = models_dict['actions'][model]['params']['kwargs']
                if action_params_labels:
                    for i, param_fit in enumerate(action_params_labels):
                        action_states_kwargs[param_fit[0]] = params_to_fit[param_fit[1]]

                a_s = models_dict['actions'][model]['object'](N, K, 
                                                             *models_dict['actions'][model]['params']['args'],
                                                             **action_states_kwargs)
                # Load action data
                a_s.load_action_data(inters, data, inters_fit)
                action_states.append(a_s)
            if len(action_states) == 1: # Must be true atm, multiple action states are not supported
                action_states = action_states[0] 

            ## Sensory states
            sensory_states = []
            for model in sensory_states_list:
                sensory_states_kwargs = models_dict['sensory'][model]['params']['kwargs']
                if sensory_params_labels:
                    for i, param_fit in enumerate(sensory_params_labels):
                        sensory_states_kwargs[param_fit[0]] = params_to_fit[param_fit[1]]
                sensory_s = models_dict['sensory'][model]['object'](N, K, 
                                                                    *models_dict['sensory'][model]['params']['args'],
                                                                    **sensory_states_kwargs)
                sensory_states.append(sensory_s)

            if len(sensory_states) == 1: # Must be true atm, multiple sensory states are not supported
                sensory_states = sensory_states[0]

            # Create agent
            if len(internal_states) == 1:
                agent = Agent(N, sensory_states, internal_states[0], action_states)
            else:
                agent = Agent(N, sensory_states, internal_states, action_states)

            # Create experiment
            experiment = Experiment(agent, external_state)

            # Fit data
            experiment.fit(console=False)

            # Extract relevant data
            # Extract posterior
            judgement_LL = -1 * internal_states[0].posterior_PF(posterior_judgement, log=True)[0]

            num_trials += 1

            if not math.isnan(judgement_LL):
                num_done += 1
                part_nLL += judgement_LL

        nLL += part_nLL
    
    print(f'nLL {np.round(nLL, 4)}, nLL per trial: {np.round(nLL/num_done, 4)}')
    print(f'Total trials: {num_trials}, Total done: {num_done}')

    return nLL/num_done