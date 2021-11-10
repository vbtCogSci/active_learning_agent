import numpy as np
import jax
from numpy.random.mtrand import uniform


class Action_state():
    def __init__(self, N, K, 
                          behaviour,
                          possible_actions,
                          action_len, 
                          policy_funcs,
                          epsilon, 
                          action_value_func):

        self._N = N
        self._n = 0
        self._K = K
        self._behaviour = behaviour

        # Num of possible action is all possible values for all variable plus 1 for staying idle
        self._num_actions = self._K * len(possible_actions) + 1

        self._action_grid = np.arange(self._K * len(possible_actions)).reshape(self._K, len(possible_actions))

        self._poss_actions = possible_actions
        self._action_len = action_len
        self._action_idx = 0
        self._current_action = self._num_actions # Represents the index of doing nothing, i.e. None, in list form 

        # Certainty parameter, stops intervening when posterior entropy is below the threshold
        self._epsilon = epsilon
 
        # A function that takes action values as arguments and return an sequence of actions which is then remapped onto action_seqs and then split using the remap_action function
        # Argument must be action values over all possible actions
        self._policy = policy_funcs[0]
        # Return the probability of taking an action given the current action values
        self._pmf_policy = policy_funcs[1]
        # Return the parameters of the policy given the the current action values
        self._params_policy = policy_funcs[2]

        # Action value function
        # Arguments must be: action_state or self, external_state, sensory_state, internal_state
        self._compute_action_values = action_value_func

        # Action values history
        self._action_values = [None for i in range(self._N+1)]
        self._planned_actions = [None for i in range(self._N+1)]

        # Set realised to False by default
        self._realised = False


    # Core method, samples an action by computing action values and selecting one action according to the given policy
    def sample(self, external_state, sensory_state, internal_state):
        # If behaviour observer, return None, else if behaviour is random, return a random action
        if self._behaviour == 'obs':
            self._n += 1
            return None
        elif internal_state.posterior_entropy < self._epsilon and self._n > 0.33*self._N:
            self._n += 1
            return None

        self._action_idx += 1
        if self._action_idx >= self._action_len or self._n == 0:
            # If policy is random return random action
            if self._behaviour == 'random':
                self._current_action = self._remap_action(np.random.choice(self._num_actions))
            else:
                # Do simulation to estimate action values if policy is not random
                action_values = self._compute_action_values(external_state, sensory_state, internal_state)

                # Sample a sequence of actions
                sampled_action = self._policy(action_values)

                # Remap to the action (idx) to tuple (variable, value)
                self._current_action = self._remap_action(sampled_action)  

                # Update hitory
                self._action_values[self._n] = action_values        

            # Reset action idx
            self._action_idx = 0

        self._n += 1
        return self._current_action
    

    # Fit action to action states
    ## Needs action data to be loaded to function
    def fit(self, external_state, sensory_state, internal_state): 
        
        if self._behaviour == 'obs':
            # Do not fit actions
    
            self._n += 1
            self._log_likelihood -= 0
            self._log_likelihood_history[self._n] = self._log_likelihood
            return 0  # Log probability of acting given that the person is an observer is necessarily - infinity

        # If action and action fit are different, do not penalise log likelihood
        if self.a and not self.a_fit:
            self._n += 1
            self._log_likelihood += 0
            self._log_likelihood_history[self._n] = self._log_likelihood
            return 0
        
        # Constraint actual action
        constrained_action = self._constrain_action(self.a)
        flat_action = self._flatten_action(constrained_action)

        if self._behaviour == 'random':
            # If behaviour is random, simply return the probability of taking any action
            self._action_idx = 0
            self._current_action = flat_action
            self._planned_actions[self._n] = flat_action
            self._n += 1

            action_log_prob = np.log(1 / self._num_actions)

            self._log_likelihood += action_log_prob
            self._log_likelihood_history[self._n] = self._log_likelihood
            return action_log_prob
        else:
            # Else do simulation to estimate action values if policy is not random
            action_values = self._compute_action_values(external_state, sensory_state, internal_state)            

            # Compute policy params
            action_prob = self._pmf_policy(flat_action, action_values)

            # Log of probability of action
            action_log_prob = np.log(action_prob)

            # Update hitory
            self._action_values[self._n] = action_values
               
            self._action_idx = 0
            self._current_action = flat_action
            self._planned_actions[self._n] = flat_action
            
            # Record history
            self._log_likelihood_history[self._n] = self._log_likelihood
            # Update log likelihood
            self._log_likelihood += action_log_prob

            self._n += 1

            return action_log_prob


    # Load data
    def load_action_data(self, actions, actions_fit, variables_values):
        self._A = actions
        self._A_fit = actions_fit
        self._X = variables_values

        self._log_likelihood = 0
        self._log_likelihood_history = np.zeros(self._N + 1)

        self._realised = True

        
    # Rollback action state
    ## Used mostly for action selection
    def rollback(self, back=np.Inf):
        if back > self._N or back > self._n:
            self._n = 0

            # Reset Action values history, Action seq hist and planned actions
            self._action_values = [None for i in range(self._N+1)]
            self._action_seqs_values = [None for i in range(self._N+1)]
            self._action_seqs = [None for i in range(self._N+1)]
            self._planned_actions = [None for i in range(self._N+1)]
        else:
            self._n -= back

            # Reset Action values, seq and planned action from n to N
            for n in range(self._n+1, self._N+1):
                self._action_values[n] = None
                self._action_seqs_values[n] = None
                self._action_seqs[n] = None
                self._planned_actions[n] = None


    @property
    def a(self):
        if np.isnan(self._A[self._n]):
            return None
        else: 
            action = int(self._A[self._n])
            return (action, self._X[self._n,:][action])

    @property
    def a_fit(self):
        if np.isnan(self._A_fit[self._n]):
            return None
        else:
            action = int(self._A_fit[self._n])
            return (action, self._X[self._n,:][action])

    @property
    def actions(self):
        return self._A[0:self._n+1]

    @property
    def actions_fit(self):
        return self._A_fit[0:self._n+1]

    
    # Return None, for idleness or a tuple (variable index, variable value) otherwise
    def _remap_action(self, action):
        if action // self._poss_actions.size > self._K - 1:
            return None
        else:
            variable_idx = action // self._poss_actions.size
            variable_value = self._poss_actions[action % self._poss_actions.size]

            return (variable_idx, variable_value)

    def _flatten_action(self, action):
        if not action:
            return self._num_actions - 1
        else:    
            value_idx = np.argmax(np.where(self._poss_actions == action[1])[0])
            return self._action_grid[action[0], value_idx]

    # Evaluate action similarity
    def _action_check(self, action_1, action_2):
        if self._constrain_action(action_2) == self._constrain_action(action_1):
            return True
        else:
            False


    def _constrain_action(self, action):
        if not action:
            return None
        else:
            set_value_idx = np.argmin(np.abs(self._poss_actions - action[1]))
            return (action[0], self._poss_actions[set_value_idx])



# Tree search action selection
class Treesearch_AS(Action_state):
    def __init__(self, N, K, behaviour, possible_actions, action_len, policy_funcs, epsilon, C, knowledge, tree_search_func, tree_search_func_args=[]):
        super().__init__(N, K, behaviour, possible_actions, action_len, policy_funcs, epsilon, self._tree_search_action_values)

        self._tree_search_func = tree_search_func
        self._tree_search_func_args = tree_search_func_args

        self._action_seqs_values = [None for i in range(self._N+1)]
        self._action_seqs = [None for i in range(self._N+1)]
        
        self._knowledge = knowledge
        self._C = C        
        

    def _tree_search_action_values(self, external_state, sensory_state, internal_state):

        # Logic for tree search based action values
        true_graph = external_state.causal_matrix

        for c in range(self._C):

            # Sample graph from posterior or use knowledge
            if type(self._knowledge) == np.ndarray:
                # Use internal_state passed as knowledge argument
                external_state.causal_matrix = internal_state._causality_matrix(self._knowledge, fill_diag=1)
            elif self._knowledge == 'perfect':
                external_state.causal_matrix = true_graph
            elif self._knowledge == 'random':
                # Sample a internal_state from a uniform distribution
                graph_c = internal_state.posterior_sample(uniform=True, as_matrix=True)
                external_state.causal_matrix = graph_c
            else:
                # Sample a internal_state from the current posterior
                graph_c = internal_state.posterior_sample(as_matrix=True)
                external_state.causal_matrix = graph_c

            # Variable for printing, sample has 
            sample_print = external_state.causal_vector
            print('Compute action values, C=', c, 'Model n:', internal_state._n, 'Sampled graph:', sample_print)

            # Build outcome tree
            seqs_values_astree = self._tree_search_func(0, external_state, 
                                                             sensory_state,
                                                             internal_state,
                                                             self._run_local_experiment,
                                                             *self._tree_search_func_args)

            # Extract action values
            leaves = jax.tree_leaves(seqs_values_astree)
            leaves_table = np.array(leaves).reshape((int(len(leaves)/2), 2))
            seqs_values_c, seqs = leaves_table[:, 0].astype(float), leaves_table[:, 1]

            # Update action_value for time n
            if c == 0:
                seqs_values = seqs_values_c
                action_seqs = seqs
            else:
                seqs_values += 1/(c+1) * (seqs_values_c - seqs_values)


        self._action_seqs_values[self._n] = seqs_values
        self._action_seqs[self._n] = action_seqs  

        # Average over values
        action_values = self._average_over_sequences(seqs_values, seqs)

        return action_values


    # Background methods
    # Update rule for the leaves values
    # Simulates an agent's update
    def _run_local_experiment(self, action_idx, external_state, sensory_state, internal_state):
        init_entropy = internal_state.posterior_entropy
        #print('init_entropy:', init_entropy, 'action:', action, 'external_state:', external_state.causal_vector)
        if internal_state._n + self._action_len >= internal_state._N:
            N = internal_state._N - internal_state._n
        else:
            N = self._action_len

        action = self._remap_action(action_idx)

        for n in range(N):
            external_state.run(interventions=action)
            sensory_state.observe(external_state, internal_state)
            internal_state.update(sensory_state, action)

        return init_entropy - internal_state.posterior_entropy

    
    def _average_over_sequences(self, seqs_values, seqs):
        first_action_in_seq = np.array([int(seq.split(',')[0]) for seq in seqs])
        action_values = np.zeros(self._num_actions)
        for i in range(self._num_actions):
            action_values[i] = seqs_values[first_action_in_seq == i].sum()

        return action_values


# Experience based action selection
## Action values are considered state independent
class Experience_AS(Action_state):
    def __init__(self, N, K, behaviour, possible_actions, action_len, policy_funcs, epsilon):
        super().__init__(N, K, behaviour, possible_actions, action_len, policy_funcs, epsilon, self._experience_action_values)

    def _experience_action_values(self, external_state, sensory_state, internal_state):
        pass


