from classes.internal_states.internal_state import Variational_IS
from scipy import stats
import numpy as np


"""
Mean field variational Agent

Holds beliefs about all parameters. Such beliefs are represented via variational distributions
This agent performs mean-field approximation:

    Q(theta_1, theta_2, ..., theta_k) = Q(theta_1)Q(theta_2)...Q(theta_k)

Updates are chosen by the active states.

Variational distribution (Qs) can be of any form but in general it is much simpler to use categorical
distribution as an expectation over their values must be computed for each update.

Theta has a normal distribution
Sigma has a discrete distribution over three values {1dt, 3dt, 6dt}
Gammas has a discrete distribution over each of the link {-1, -1/2, 0, 1/2, 1}.
Dalston Kingsland, London E8 2FAhack
One needs to create an indexed representation of such Qs with:
- Distributions types (Gaussian, discrete): to know how to update
- Entropies: to select which distribution to update
- Rules of update for each (function?) that given data and others Qs can compute the updated parameters

Rules of updates are function that update parameters and are called if the index of the Qs in the boolean selector 
from active states is set to True 
- Need a generic update if all distributions are discrete
- Need a specific update if theta is Gaussian: should be faster as less combinatorially complex

"""


class MeanField_VIS(Variational_IS):
    def __init__(self, N, K, links, dt, parameter_set, certainty_threshold=1e-1, generate_sample_space=True, prior_param=None, smoothing=False):
        super().__init__(N, K, links, dt, parameter_set, self._update_rule, generate_sample_space=generate_sample_space, prior_param=prior_param, smoothing=smoothing)

        self._epsilon = certainty_threshold

    # Update rule
    def _update_rule(self, sensory_state, action_state):
        """
        Action state should hold a specific parameter for the variational agent.
        A indicator vector stating which factor to update
        
        For each selected factor
            Use obsrved data and depend factor to update it
            If link value, use all non link factors and all other factors sharing the same effect
            Else, use all other non link factor and all factors have the current intervened variable as a cause
        """

        action_fromstate = action_state.a
        if not action_fromstate:
            return self._posterior_params
        else:
            action = action_fromstate[0]

        X = sensory_state.s
        X_prev = sensory_state.s_prev

        # Update all each data point 
        #self._update_schedule = np.ones(self._num_factors, dtype=bool)
        self._update_schedule[~self._link_params_bool] = 1 

        params_to_update = self._param_names_list[self._update_schedule]
        params_to_update_indices = self._param_index_list[self._update_schedule]

        dependencies_str = [None for _ in params_to_update]
        dependencies_array = np.zeros((len(dependencies_str), self._update_schedule.size), dtype=bool)

        var_to_consider = np.zeros((params_to_update.size, self._K), dtype=bool)

        for i, param in enumerate(params_to_update):
            
            # If agent is intervening on the cause the factor, do not update it
            if param in self._param_names_list[self._link_params_bool]:
                if action == int(param[-1]):
                    continue

            dependencies_str[i] = self._parameter_set[param]['dependencies_as_str']
            dependencies_array[i, :] = self._parameter_set[param]['dependencies_as_bool']

            if self._parameter_set[param]['type'] == 'no_link':
                dep_bool = np.zeros(self._link_names_matrix.shape, dtype=bool)
                for j in range(self._K):
                    for k in range(self._K):
                        if j != k and k != action:
                            dep_bool[j, k] = 1
                additional_dependencies = self._link_names_matrix[dep_bool]
                add_dep_bool = np.in1d(self._param_names_list, additional_dependencies)
                dependencies_str[i] = np.concatenate((dependencies_str[i], additional_dependencies), dtype=object)
                dependencies_array[i, :][add_dep_bool] = 1

                var_to_consider[i, :] = np.ones(self._K, dtype=bool)
                var_to_consider[i, action] = 0
            else:
                var_to_consider[i, int(params_to_update[i][-1])] = 1

            # Now that dependencies needed to update have been found
            ## Generate a list of all parameter values and the associated joints
            dep_str = ','.join(dependencies_str[i])
            parameter_values = self._param_subsets_dict[dep_str]
            expectation_probabilities = self._construct_parameter_combinations(dependencies_str[i], self.variational_posterior[dependencies_array[i, :]])

            # Perform the update
            # Compute the expectation
            if param in  self._param_names_list[self._link_params_bool]:
                expectation_quantities = self._causal_link_expectation(param, self._parameter_set[param]['values'], X, X_prev, dependencies_str[i].tolist(), parameter_values, var_to_consider[i, :])
            else:
                expectation_quantities = self._parameter_expectation(param, self._parameter_set[param]['values'], X, X_prev, dependencies_str[i].tolist(), parameter_values, var_to_consider[i, :])

            # Unnormalised probability of observing this transition
            data_log_probability_unnormalised = np.sum(expectation_probabilities.prod(axis=1) * expectation_quantities, axis=1)
            
            # Update considered belief
            if not action_state.simulate:
                a = 1
                pass
            self._posterior_params[params_to_update_indices[i]] += data_log_probability_unnormalised
            #self._posterior_params[params_to_update_indices[i]] - np.amax(self._posterior_params[params_to_update_indices[i]])

        # Reset update schedule.
        self._reset_update_schedule(simulate=action_state.simulate)
        
        if not action_state.simulate:
            a = 1
            pass
        return self._posterior_params

    """
    Prior initialisation specific to model
    """
    def _local_prior_init(self):
        non_causal = [np.log(self._parameter_set[nc_factor]['prior']) for nc_factor in self._param_names_list[~self._link_params_bool]]
        causal_links = [np.log(factor) for factor in self._prior_params]
        self._prior_params = np.array(non_causal + causal_links, dtype=object)

        # Initialise update schedule
        self._init_update_schedule()

    """
    Resets the update schedule based on the information gained
    """
    def _init_update_schedule(self):
        
        self._update_schedule = np.zeros(self._num_factors, dtype=bool)
        prior_entropy = np.array([self._entropy(self._likelihood(factor)) for factor in self._prior_params])
        select = np.random.choice(np.arange(prior_entropy.size), p=np.ones(prior_entropy.size)/prior_entropy.size)
        self._update_schedule[select] = 1

        # Init history and set first entry to fist
        self._update_schedule_history = np.zeros((self._N+1, self._num_factors))
        self._update_schedule_history[self._n, :] = self._update_schedule



    def _reset_update_schedule(self, update_schedule=None, simulate=False):
        # Do nothing if simulating action
        if simulate:
            return

        # Save update schedule to history
        self._update_schedule_history[self._n, :] = self._update_schedule

        # Update schedule
        if not type(update_schedule) == np.ndarray:
            update_schedule = self._update_schedule

        if np.sum(update_schedule) == 0:
            # If the agent has no schedule, set one based on the most uncertain parameter
            self._update_schedule[np.argmax(self.variational_posterior_entropy)] = 1
        elif np.sum(update_schedule) == 1:
            # If the agent is certain enough, change goal, otherwise do nothing
            if self.variational_posterior_entropy[self._update_schedule] < self._epsilon:
                self._update_schedule = np.zeros(self._num_factors, dtype=bool)
                self._update_schedule[np.argmax(self.variational_posterior_entropy)] = 1
        else:
            # Check each entropy
            certainty = np.logical_and(self._update_schedule, self.variational_posterior_entropy < self._epsilon)
            
            if np.sum(certainty) == np.sum(self._update_schedule):
                # if all certainty threshold are met, reset schedule
                ## Currently only sets one factor
                self._update_schedule = np.zeros(self._num_factors, dtype=bool)
                self._update_schedule[np.argmax(self.variational_posterior_entropy)] = 1
            elif np.sum(certainty) > 0:
                # If some have reached, simply remove the factors from the schedule
                self._update_schedule[certainty] = 0

            

    """
    Update functions for causal link and other parameters
    """
    def _causal_link_expectation(self, belief_name, belief_values, X, X_prev, parameter_names, parameter_values, var_to_consider):
        
        out = np.zeros((belief_values.size, parameter_values.shape[0]))
        for k in range(self._K):
            if var_to_consider[k] == 0:
                continue
            
            current_var = np.zeros(self._K).astype(bool)
            current_var[k] = 1

            sigmas = parameter_values[:, parameter_names.index('sigma')]
            thetas = parameter_values[:, parameter_names.index('theta')]

            links = np.ones((belief_values.size, self._K, parameter_values.shape[0]))
            
            links[:, ~current_var, :] = np.tile(parameter_values[:, 2:], (belief_values.size, 1, 1)).reshape((belief_values.size, parameter_values[:, 2:].shape[1], parameter_values[:, 2:].shape[0]))
            bvs = np.tile(belief_values, (parameter_values[:, 2:].shape[0], 1)).T
            links[:, int(belief_name[0]), :] = bvs

            regularisor = -1 * X_prev[k] * (np.abs(X_prev[k]) / 100)

            mus = thetas * (X_prev @ links + regularisor - X_prev[k]) * self._dt

            out += stats.norm.logpdf(X[k] - X_prev[k], loc=mus, scale=sigmas*np.sqrt(self._dt))

        return out 


    def _parameter_expectation(self, belief_name, belief_values, X, X_prev, parameter_names, parameter_values, var_to_consider):
        
        out = np.zeros((belief_values.size, parameter_values.shape[0]))
        for k in range(self._K):
            if var_to_consider[k] == 0:
                continue
            
            current_var = np.zeros(self._K).astype(bool)
            current_var[k] = 1

            if belief_name == 'sigma':
                thetas = parameter_values[:, parameter_names.index('theta')]
                sigmas = belief_values
            else:
                sigmas = parameter_values[:, parameter_names.index('sigma')]
                thetas = belief_values

            links_indices = [parameter_names.index(param) for param in parameter_names[1:] if int(param[-1]) == k]
            #print(links_indices)
            links = np.ones((self._K, parameter_values.shape[0]))
            links[~current_var, :] = parameter_values[:, links_indices].T

            regularisor = -1 * X_prev[k] * (np.abs(X_prev[k]) / 100)

            if belief_name == 'theta':
                mus = thetas.reshape((thetas.size, 1)) * (X_prev @ links + regularisor - X_prev[k]) * self._dt
                out += stats.norm.logpdf(X[k] - X_prev[k], loc=mus, scale=sigmas*np.sqrt(self._dt))
            else:
                mus = thetas * (X_prev @ links + regularisor - X_prev[k]) * self._dt
                out += stats.norm.logpdf(X[k] - X_prev[k], loc=mus, scale=sigmas.reshape((sigmas.size, 1))*np.sqrt(self._dt))

        return out


    

    

        