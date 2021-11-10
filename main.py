import numpy as np
import pandas as pd
import pickle

from classes.ou_network import OU_Network

from classes.internal_states.lc_omniscient_DIS import Local_computations_omniscient_DIS
from classes.internal_states.lc_omniscient_CIS import Local_computations_omniscient_CIS
from classes.internal_states.normative_DIS import Normative_DIS

from classes.action_states.discounted_gain_soft_horizon_TSAS import Discounted_gain_soft_horizon_TSAS
from classes.action_states.undiscounted_gain_hard_horizon_TSAS import Undiscounted_gain_hard_horizon_TSAS

from classes.sensory_states.omniscient_ST import Omniscient_ST

from classes.agent import Agent
from classes.experiment import Experiment

from methods.policies import softmax_policy_init
from methods.empirical_priors import generate_discrete_empirical_priors, generate_gaussian_empirical_priors




def main():
    ## Import behavioural experiment
    with open('/home/vbtesh/documents/CompProjects/vbtCogSci/csl2analysis/data/csl_2_modelling_data.obj', 'rb') as inFile:
        modelling_data = pickle.load(inFile)


    part_key = '5ef109c89196fa6d5cf6c005'
    conditions = ['generic', 'congruent', 'incongruent', 'implausible']
    cond = conditions[0]
    

    # Model fitting
    fitting = True # If false, no data will be used 

    ## Data from trial
    part_data = modelling_data[part_key]['trials'][cond]
    posterior = part_data['posterior']
    data = part_data['data']
    inters = part_data['inters']
    inters_fit = part_data['inters_fit']
    judgement_data = part_data['links_hist']


    # General model parameters (true for all trials)
    if fitting:
        N = data.shape[0] - 1
        K = data.shape[1]
    else:
        N = 300
        K = 3
    links = np.array([-1, -0.5, 0, 0.5, 1])
    theta = 0.5
    dt = 0.2
    sigma = 3

    smoothing = 1e-20
    #smoothing = False

    # Set up priors
    flat_prior = np.array([0.2, 0.2, 0.2, 0.2, 0.2])
    flat_prior = np.tile(flat_prior, (6, 1))

    random_prior = np.random.rand(6, 5)
    random_prior = random_prior / random_prior.sum(axis=1).reshape((6, 1))

    prior_perfect = np.array([[1, 0, 0, 0, 0],
                             [0, 0, 1, 0, 0],
                             [0, 0, 1, 0, 0],
                             [1, 0, 0, 0, 0],
                             [0, 0, 1, 0, 0],
                             [0, 0, 1, 0, 0]])
    # Emprical Priors
    if 'prior' in part_data.keys():
        part_map = part_data['prior'] # Participant's maximum a priori
        temp = 5 # Must be explored further
        sd = 1e5
        discrete_empirical_prior, discrete_prior_entropy = generate_discrete_empirical_priors(part_map, links, temp)
        continuous_empirical_prior, continuous_prior_entropy = generate_gaussian_empirical_priors(part_map, sd)
    else:
        discrete_empirical_prior = random_prior
        sd = 1e5
        continuous_empirical_prior = np.array([[0, 0, 0, 0, 0, 0],
                                               [sd, sd, sd, sd, sd, sd]]).T

    ## Final prior assignment
    prior = discrete_empirical_prior

    #print(prior**prior_sample_size)

    # Ground truth model
    ## Import from behavioural experiment
    gt_behavioural_exp = part_data['ground_truth']
    ## Any model as np.ndarray
    custom_model = np.array([-1, 0.5, .0, -1, 0, 0])
    ## Final ground truth assignment
    true_model = gt_behavioural_exp
    #true_model = custom_model

    # Action parameters
    ## Number of model to sample from the posterior
    C = 3
    ## Different action possibility
    poss_actions = np.arange(-100, 100)
    poss_actions = np.array([85, 45, 0, -45, -85])
    poss_actions = np.arange(-100, 101, step=10)
    ## Define action length (TO BE REFINED FOR FITTING DATA)
    action_len = 5 
    ## Policy for action selection from action values
    policy_funcs = softmax_policy_init(1) # Returns three function: sample, pmf, params
    ## Parameters
    epsilon = 1e-2 # Certainty threshold: agent stops intervening after entropy goes below epsilon
    knowledge = False  # Can be a model as nd.array, True for perfect knowledge, 'random' for random sampling and False for posterior based sampling
    ## Special parameters for tree searches
    horizon = 1e-2 # For soft horizon discounted gain
    discount = 0.01 # For soft horizon discounted gain
    depth = 1 # Horizon for hard horizon undiscounted gain
    ## General behaviour parameter
    behaviour = 'obs'   # Can be 'obs', 'random' or 'actor'
    

    sensory_state = Omniscient_ST(N, K)
    
    action_state = Discounted_gain_soft_horizon_TSAS(N, K, behaviour, poss_actions, action_len, policy_funcs, epsilon, C, knowledge, discount, horizon)
    action_state = Undiscounted_gain_hard_horizon_TSAS(N, K, behaviour, poss_actions, action_len, policy_funcs, epsilon, C, knowledge, depth)
    
    internal_state = Normative_DIS(N, K, prior, links, dt, theta, sigma, sample_params=False, smoothing=smoothing)
    internal_state = Local_computations_omniscient_DIS(N, K, prior, links, dt, theta, sigma, sample_params=False, smoothing=smoothing)
    internal_state = Local_computations_omniscient_CIS(N, K, continuous_empirical_prior, dt, theta, sigma)

    external_state = OU_Network(N, K, true_model, theta, dt, sigma)

    agent = Agent(N, sensory_state, internal_state, action_state)

    if fitting:
        external_state.load_trial_data(data)
        action_state.load_action_data(inters, inters_fit, data)
        internal_state.load_judgement_data(judgement_data, posterior)

    experiment = Experiment(agent, external_state)

    # Run experiment
    if fitting:
        experiment.fit()
    else:
        experiment.run()

    pass


if __name__ == '__main__':
    main()

pass

