import numpy as np

import numpy


# from dolo import *
import pickle

# should be moved to markov
from numba import jit, njit
from dolo.numeric.grids import EmptyGrid, CartesianGrid, UnstructuredGrid

@njit
def choice(x, n, cumul):
    i = 0
    running = True
    while i<n and running:
        if x < cumul[i]:
            running = False
        else:
            i += 1
    return i


@jit
def simulate_markov_chain(nodes, transitions, i_0, n_exp, horizon):

    n_states = nodes.shape[0]

#    start = numpy.array( (i_0,)*n_exp )
    simul = numpy.zeros( (horizon, n_exp), dtype=int)
    simul[0,:] = i_0
    rnd = numpy.random.rand(horizon* n_exp).reshape((horizon,n_exp))

    cumuls = transitions.cumsum(axis=1)
    cumuls = numpy.ascontiguousarray(cumuls)

    for t in range(horizon-1):
        for i in range(n_exp):
            s = simul[t,i]
            p = cumuls[s,:]
            simul[t+1,i] = choice(rnd[t,i], n_states, p)

    res = numpy.row_stack(simul)

    return res

class Process:
    pass

class IIDProcess(Process):
    pass

class DiscreteProcess(Process):
    pass

class ContinuousProcess(Process):
    pass

# class VAR1(ContinuousProcess):
#     pass

class DiscretizedProcess:
    pass

class DiscretizedIIDProcess(DiscretizedProcess):

    def __init__(self, nodes, weights):
        self.integration_nodes = nodes
        self.integration_weights = weights

    @property
    def grid(self):
        return EmptyGrid()

    def n_nodes(self): # integer
        return 1

    def node(self, i:int): # vector
        return self.integration_nodes[0,:]*0

    def n_inodes(self, i:int): # integer
        return self.integration_nodes.shape[0]

    def inode(self, i:int, j:int): # vector
        return self.integration_nodes[j,:]

    def iweight(self, i:int, j:int): # scalar
        return self.integration_weights[j]


class MvNormal(IIDProcess):

    def __init__(self, Sigma=None, orders=None, mu=None):

        self.Sigma = np.atleast_2d( np.array(Sigma, dtype=float) )
        self.d = len(self.Sigma)
        if orders is None:
            self.orders = np.array([5]*self.d)
        else:
            self.orders = np.array(orders, dtype=int)
        if mu is None:
            self.mu = np.array([0.0]*self.d)
        else:
            self.mu = np.array(mu, dtype=float)
        assert(self.Sigma.shape[0] == self.d)
        assert(self.Sigma.shape[0] == self.d)
        assert(self.orders.shape[0] == self.d)

    def discretize(self, orders=None):
        if orders is None:
            orders = self.orders
        from dolo.numeric.discretization.quadrature import gauss_hermite_nodes
        [x, w] = gauss_hermite_nodes(orders, self.Sigma, mu=self.mu)
        x = np.row_stack( [(e + self.mu) for e in x] )
        return DiscretizedIIDProcess(x,w)

    def simulate(self, N, T, m0=None, stochastic=True):
        from numpy.random import multivariate_normal
        Sigma = self.Sigma
        mu = self.mu
        if stochastic:
            sim = multivariate_normal(mu, Sigma, N*T)
        else:
            sim = mu[None,len(mu)].repeat(T*N,axis=0)
        return sim.reshape((T,N,len(mu)))

    def response(self, T, impulse):
        from numpy.random import multivariate_normal
        Sigma = self.Sigma
        mu = self.mu
        irf = numpy.zeros((T,len(mu)))
        irf[1,:] = impulse[None,:]
        return irf



class DiscreteMarkovProcess(DiscretizedProcess):

    # transitions: 2d float array
    # values: 2d float array

    def __init__(self, transitions, values):

        self.transitions = np.array(transitions, dtype=np.float64)
        self.values = np.array(values, dtype=np.float64)

    def discretize(self):
        return self

    @property
    def grid(self):
        return UnstructuredGrid(self.values)

    def n_nodes(self): # integer
        return self.values.shape[0]

    def node(self, i:int): # vector
        return self.values[i,:]

    def nodes(self):
        return self.values

    def n_inodes(self, i:int): # integer
        return self.transitions.shape[1]

    def inode(self, i:int, j:int): # vector
        return self.values[j,:]

    def iweight(self, i:int, j:int): # scalar
        return self.transitions[i,j]

    def simulate(self, N, T, i0=0, stochastic=True):
        if stochastic:
            inds = simulate_markov_chain(self.values, self.transitions, i0, N, T)
        else:
            inds = np.zeros((T,N), dtype=int) + i0
        return self.values[inds]
#
# class MarkovChain(list):
#
#     def __init__(self, P=None, Q=None):
#
#         import numpy
#         P = numpy.array(P, dtype=float)
#         Q = numpy.array(Q, dtype=float)
#         self.states = P
#         self.transitions = Q
#         self.extend([P, Q]) # compatibility fix
# #


class MarkovProduct(DiscreteMarkovProcess):

    def __init__(self, M1=None, M2=None):

        self.M1 = M1
        self.M2 = M2

    def discretize(self):

        M1 = self.M1.discretize()
        M2 = self.M2.discretize()
        from dolo.numeric.discretization import tensor_markov
        [P, Q] = tensor_markov(
            (M1.values, M1.transitions),
            (M2.values, M2.transitions) )
        return DiscreteMarkovProcess(Q,P)

class VAR1(DiscreteMarkovProcess):

    def __init__(self, rho=None, Sigma=None, mu=None, N=3):

        self.Sigma = np.atleast_2d(Sigma)
        d = self.Sigma.shape[0]
        rho = np.array(rho)
        if rho.ndim == 0:
            self.rho = np.eye(d)*rho
        elif rho.ndim ==1:
            self.rho = np.diag(rho)
        else:
            self.rho = rho
        if mu is None:
            self.mu = np.zeros(d)
        else:
            self.mu = np.array(mu, dtype=float)
        self.d = d

    def discretize(self, N=3):

        rho = self.rho
        Sigma = self.Sigma

        try:
            assert(abs(np.eye(rho.shape[0])*rho[0,0]-rho).max() <= 1)
        except:
            raise Exception("When discretizing a Vector AR1 process, the autocorrelation coefficient must be as scalar. Found: {}".format(rho_array))

        from dolo.numeric.discretization import multidimensional_discretization

        [P,Q] = multidimensional_discretization(rho[0,0], Sigma, N=N)

        P += self.mu[None,:]

        return DiscreteMarkovProcess(values=P, transitions=Q)


    def simulate(self, N, T, m0=None, stochastic=True):

        d = self.d

        if m0 is None:
            m0 = np.zeros(d)
        from numpy.random import multivariate_normal
        Sigma = self.Sigma
        mu = self.mu*0
        if stochastic:
            innov = multivariate_normal(mu, Sigma, N*T)
        else:
            innov = mu[None,len(mu)].repeat(T*N,axis=0)
        innov = innov.reshape((T,N,d))
        rho = self.rho
        sim = np.zeros((T,N,d))
        sim[0,:,:] = m0[None,:]
        for t in range(1,sim.shape[0]):
            sim[t,:,:] = sim[t-1,:,:]@rho.T + innov[t,:,:]

        sim += self.mu[None,None,:]

        return sim

    def response(self, T, impulse):
        d = self.d
        irf = np.zeros((T,d))
        irf[0,:] = impulse
        rho = self.rho
        for t in range(1,irf.shape[0]):
            irf[t,:] = rho@irf[t-1,:]
        irf += self.mu[None,:]
        return irf
