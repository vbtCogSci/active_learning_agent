from classes.internal_states.internal_state import Discrete_IS
from scipy import stats
import numpy as np

# Local computation discrete agent
class Local_computations_omniscient_DIS(Discrete_IS):
    def __init__(self, N, K, prior_params, links, dt, theta, sigma, sample_params=True, smoothing=False):
        super().__init__(N, K, prior_params, links, dt, theta, sigma, self._update_rule, sample_params=sample_params, smoothing=smoothing)

        self._prior_params = np.log(prior_params)
        self._init_priors()

        # Special parameters for faster computations
        self._links_lc_updates = np.tile(links.reshape((links.size, 1)), 3).T

        # Define own attractor mu, should be mu for each given the other two
        self._mus = self._attractor_mu(np.zeros(self._K))
        #self._mus_history = [None for i in range(self._N)]

        

    def _update_rule(self, sensory_state, action_state):
        intervention = action_state.a
        obs = sensory_state.s

        # Logic for updating
        log_likelihood_per_link = np.zeros(self._prior_params.shape)
        idx = 0
        for i in range(self._K):
            for j in range(self._K):
                if i != j:
                    # Likelihood of observed the new values given the previous values for each model
                    log_likelihood = stats.norm.logpdf(obs[j], loc=self._mus[idx, :], scale=self._sigma*np.sqrt(self._dt))
                    # Normalisation step
                    likelihood_log = log_likelihood - np.amax(log_likelihood)
                    likelihood_norm = np.exp(likelihood_log) / np.exp(likelihood_log).sum()

                    ## If intervention, the probability of observing the new values is set to 1
                    if isinstance(intervention, tuple):
                        if j == intervention[0]:
                            likelihood_norm[:] = 1

                    log_likelihood_per_link[idx, :] = np.log(likelihood_norm)
                    idx += 1
        
        # Posterior params is the log likelihood of each model given the data
        log_posterior = self._posterior_params + log_likelihood_per_link

        # update mus
        self._update_mus(obs)

        return log_posterior

    
    # Background methods
    def _update_mus(self, obs):
        #self._mus_history[self._n] = self._mus
        self._mus = self._attractor_mu(obs)

    
    def _attractor_mu(self, obs):
        mu_self = obs * (1 - np.abs(obs) / 100)
        mu_att = obs.reshape((self._K, 1)) * self._links_lc_updates

        mus = np.zeros((self._K**2 - self._K, self._L.size))
        idx = 0
        for i in range(self._K):
            for j in range(self._K):
                if i != j:
                    mus[idx, :] = obs[j] + (mu_att[i, :] + mu_self[j] - obs[j]) * self._dt * self._theta
                    idx += 1

        return mus

