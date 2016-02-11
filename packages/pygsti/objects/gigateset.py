#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation              
#    This Software is released under the GPL license detailed    
#    in the file "license.txt" in the top-level pyGSTi directory 
#*****************************************************************
""" Defines the GateSet class and supporting functionality."""

import itertools as _itertools
import warnings as _warnings
import numpy as _np
import numpy.linalg as _nla
import numpy.random as _rndm
import scipy as _scipy
import collections as _collections

from ..tools import matrixtools as _mt
from ..tools import basistools as _bt
from ..tools import gatetools as _gt
from ..tools import likelihoodfns as _lf
from ..tools import jamiolkowski as _jt

#import evaltree as _evaltree
import gate as _gate
import gateset as _gateset

class GaugeInvGateSet(object):  #(_collections.OrderedDict):
    """
    Encapsulates a set of gate, state preparation, and POVM effect operations
     in a gauge-invariant manner.

    A GaugeInvGateSet stores a gateset using a *minimal* gauge-invariant
    representation.
    """
    
    def __init__(self,items=[]):
        """ 
        Initialize a gauge-invariant gate set, possibly from a list of
          items (used primarily by pickle) 
        """
        self.gate_dim = None
        self.E_params = None
        self.D_params = []
        self.B0_params = []
        self.gateLabels = []
        self.storedY0 = None

    def from_gateset(self, gateset, verbosity=0):
        """        
        Initialize a gauge-invariant gate set from an existing (gauge-
         variant) GateSet.
        """

        #This only works for fully-parameterized GateSets so far...
        #assert(gates == True and G0 == True and SPAM == True and SP0 == True)
        #assert(all([isinstance(g, _gate.FullyParameterizedGate)
        #            for g in gateset.values() ]))

        vb = verbosity #shorthand
        self.gate_dim = gateset.get_dimension()
        #self.evstruct = evstruct #eigenvalue structure: a string of "R"s and 
        #                         # "C"s for real-pair and conjugate-pair.


        self.gateLabels = gateset.keys()
        gl0 = self.gateLabels[0] #plays a special role
        
        self.D_params = [None]*len(self.gateLabels)
        Y = [None]*len(self.gateLabels) #List of eigenvector mxs

        #Get parameterization of gate eigenvalues (and get corresponding
        #  eigenvector matrices for later use)
        for i,gl in enumerate(self.gateLabels):
            self.D_params[i], Y[i] = _parameterize_real_gate_mx(gateset[gl],vb)

        #DEBUG
        #print "DB: Y0 = "; _mt.print_mx(Y[0])
        #print "DB: invY0 = "; _mt.print_mx(_np.linalg.inv(Y[0]))
        #print "DB: rho = "; _mt.print_mx(gateset.rhoVecs[0])

        #Get parameterization of SPAM pair (assume just a single pair is
        # present for now)
        rho_tilde = _np.dot(_np.linalg.inv(Y[0]), gateset.rhoVecs[0])
        delta0_diag = _get_delta0_diag(rho_tilde, self.D_params[0], vb)
        delta0 = _np.diag( delta0_diag )
        scaledY0 = _np.dot( Y[0], delta0 )
        
        #remember the "gauge" of this gateset for going back to a 
        # gauge-dependent gateset.
        self.storedY0 = scaledY0 

        #Make sure scaling rho_tilde gives vector of all 1s
        assert( _np.allclose( _np.dot( _np.diag(1.0/delta0_diag), rho_tilde),
                              _np.ones(rho_tilde.shape)))

        ET_tilde = _np.dot( _np.transpose(gateset.EVecs[0]), scaledY0 )
        self.E_params = _get_ET_params(ET_tilde, self.D_params[0])
           #FUTURE: multiple E-vectors allowed?

        #assume a SPAM pair is present and parameterized (for now) - so
        # parameterize B0j matrices all the same.
        self.B0_params = [None]*(len(self.gateLabels))
        for j,gl in enumerate(self.gateLabels[1:],start=1):
            invYjY0 = _np.dot( _np.linalg.inv(Y[j]), scaledY0 )
            self.B0_params[j] = _get_B_params(invYjY0, self.D_params[j],
                                              self.D_params[0])
                           
        
    def to_gateset(self,verbosity=0):
        """
        Create a gauge-variant GateSet from this gauge-invariant
        representation
        """

        #We're free to assume some Y0 (~choosing a gauge).  We use the one
        # stored during from_gateset for now.  We *could* choose something
        # else if we wanted (or never stored one) -- it's cols just have to
        # have the correct conjugate-pair structure (given by D_params[0])
        Y0 = self.storedY0 
        invY0 = _np.linalg.inv(Y0)
        vb = verbosity #shorthand

        #Create the gate set
        gs = _gateset.GateSet()

        #Set rho
        fixed_rhoTilde = _np.ones( (self.gate_dim,1), 'd' )
        gs.set_rhovec( _np.dot(Y0,fixed_rhoTilde) )

        #Set E (FUTURE: multiple allowed?)
        ETilde = _get_ETilde_vector( self.E_params, self.D_params[0] )
        Evec = _np.dot(_np.transpose(invY0),ETilde)
        assert( all(_np.isreal(Evec)) ) # b/c of conjugacy structure
        gs.set_evec( _np.real(Evec) ) 

        #Set initial gate
        D0 = _constructDj(self.D_params[0])
        mx = _np.dot( Y0, _np.dot(D0, invY0) )
        gs.set_gate(self.gateLabels[0], _gate.FullyParameterizedGate(mx))

        #Set remaining gates
        for i,gl in enumerate(self.gateLabels[1:],start=1):
            mx = _deparameterize_real_gate_mx(self.D_params[i],
                                              self.D_params[0],
                                              self.B0_params[i],
                                              Y0, vb)
            gs.set_gate(gl, _gate.FullyParameterizedGate(mx))

        #Set identity vector (store it upon creation?)

        #Return constructed gate set
        return gs


    def from_vector(self, v, gates=True,G0=True,SPAM=True,SP0=True):
        k = 0
        dim = self.gate_dim
        self.E_params = v[k:k+dim]; k += dim
        for i in range(len(self.D_params)):
            self.D_params[i] = v[k:k+dim]; k += dim

        assert(self.B0_params[0] is None) # just a placeholder
        for i in range(1, len(self.B0_params)):
            L = len(self.B0_params[i])
            self.B0_params[i] = v[k:k+L]; k += L
            #TODO: test length L against what it should be

    def to_vector(self, gates=True,G0=True,SPAM=True,SP0=True):
        #concat self.E_params, self.D_params, self.B0_params into one vector
        assert(len(self.E_params) == self.gate_dim)
        assert( all([len(Dp) == self.gate_dim for Dp in self.D_params]))
        to_concat = [self.E_params] + self.D_params + self.B0_params[1:]
        return _np.concatenate(to_concat)

    def num_params(self,gates=True,G0=True,SPAM=True,SP0=True):
        return len(self.to_vector())

    def num_nongauge_params(self,gates=True,G0=True,SPAM=True,SP0=True):
        return self.num_params(gates,G0,SPAM,SP0)

    def num_gauge_params(self,gates=True,G0=True,SPAM=True,SP0=True):
        return 0



def _parameterize_real_gate_mx(real_gate_mx, verbosity):
    """ 
    Convert the possibly complex eigenvalues of a real matrix into
    the purely real gauge-inv-gateset parameters.
    """

    #Get (complex) eigenvalues and eigenvectors
    evals,evecs = _np.linalg.eig(real_gate_mx)

    #find complex-conjugate (or real degenerate) eigenvalue pairs
    conjugate_pairs = []
    for i,v in enumerate(evals):
        if any([ i in p for p in conjugate_pairs]): continue
        for j,w in enumerate(evals[i+1:],start=i+1):
            if any([ j in p for p in conjugate_pairs]): continue
            if _np.isclose(v.conj(), w): 
                conjugate_pairs.append( (i,j) )
                if _np.isreal(v): #special case of degenerate evals
                    V = evecs[:,i].copy(); W = evecs[:,j].copy()
                    if all(_np.isreal(V)) and all(_np.isreal(W)):
                        #we treat all degen. eigenvals as conjugate-pairs,
                        # so want conjugate-pair, not real eigenvectors:
                        evecs[:,i] = (V + 1j*W); evecs[:,j] = (V - 1j*W)
                        evecs[:,i] /= _np.linalg.norm(evecs[:,i])
                        evecs[:,j] /= _np.linalg.norm(evecs[:,j])
                        
    
    #put remaining (non-conj-pair) indices ==> real_pairs
    remaining = [ i for i in range(len(evals)) if \
                      not any([ i in p for p in conjugate_pairs]) ]
    assert(all([ _np.isreal(evals[i]) for i in remaining ]))

    nLeft = len(remaining)
    real_pairs = [(remaining[i],remaining[i+1]) for i in range(0,nLeft-1,2)]
    
    #create array of eigenvalue parameters, keeping track of the
    # needed eigenvector permutation given the new eigenvalue ordering.
    eval_params = _np.empty( evals.shape, 'd' ) # Note: *not* complex
    permMx = _np.zeros(evecs.shape, 'd')
    k = 0 #running index of current eigenvalue after re-arrangement

    for i,j in conjugate_pairs:
        if evals[i].imag > evals[j].imag: # i => k, j => k+1
            permMx[i,k] = 1.0; permMx[j,k+1] = 1.0
        else: # j => k, i => k+1 (lower index always has greater imag part)
            permMx[i,k] = 1.0; permMx[j,k+1] = 1.0
        eval_params[k] = evals[i].real
        eval_params[k+1] = -abs(evals[i].imag) # neg => conj. pair
        k += 2

    for i,j in real_pairs:
        if evals[i] > evals[j]: # i => k, j => k+1
            permMx[i,k] = 1.0; permMx[j,k+1] = 1.0
        else: # j => k, i => k+1 (lower index always is greater value)
            permMx[i,k] = 1.0; permMx[j,k+1] = 1.0
        eval_params[k] = (evals[i].real + evals[j].real) / 2.0
        eval_params[k+1] = abs(evals[i].real - 
                               evals[j].real) / 2.0 # pos => real pair
        k += 2

    if len(remaining) % 2 == 1: #if there's one un-paired (real) eval
        assert(_np.isreal(evals[remaining[-1]]))
        permMx[remaining[-1],k] = 1.0
        eval_params[k] = evals[remaining[-1]].real

    if verbosity > 3:
        print "Parameterizing matrix:"; _mt.print_mx(real_gate_mx)
        print " -> Eigenvalues: ";_mt.print_mx(evals)
        print " -> Parameters: ";_mt.print_mx(eval_params)
        print " -> Evec Permutation Mx  = ";_mt.print_mx(permMx)
        print " -> Y-Mx  = ";_mt.print_mx(_np.dot(evecs, permMx))
        print ""

    new_evecs = _np.dot(evecs, permMx)
    return eval_params, new_evecs
        

def _get_delta0_diag(rho_tilde, D0_params, verbosity):

    #Note: 
    # rho-tilde has form inv(Y0) * rho, where inv(Y0) has conjugate-paired
    # rows as determined by the eigenvalue parameters D0_params and rho
    # is a real column vector.  Thus, inv(Y0) * rho is a complex column
    # vector with the conjugate-pair structure given by D0_params.  Thus,
    # the diagonal of inv(delta0) (or just delta0 since it's a diag mx)
    # will have this same structure, to preserve the conjugate-pair 
    # structure of rho-tilde and the B-matrices.
    rho_tilde = rho_tilde.flatten() #so we can index using a single index
    inv_delta0_diag = _np.empty(len(rho_tilde),'complex')

    if verbosity > 3:
        print "Finding delta0"
        print " rho-tilde = ";_mt.print_mx(rho_tilde)
        print " D0-params = ";_mt.print_mx(D0_params)

    #We compute the diagonal of inv(delta0) which makes
    # inv(delta0) * inv(Y0) * rho = vector of all ones
    for i in range(0,len(D0_params)-1,2):
        a,b = D0_params[i:i+2]
        if b <= 0: 
            # complex-conj pair at index i,i+1, so:
            assert(_np.isclose(rho_tilde[i],rho_tilde[i+1].conj()))
            if abs(rho_tilde[i]) < 1e-10:
                print "Warning1: scaling near-zero rho_tilde element to 1.0!"
                inv_delta0_diag[i] = 1e10 # ~= 1 / 1e-10
            else:
                inv_delta0_diag[i] = (1.0+0j) / rho_tilde[i] #complex division
            inv_delta0_diag[i+1] = inv_delta0_diag[i].conj()
        else:
            # real pair at index i,i+1, so:
            assert(_np.isreal(rho_tilde[i]) and _np.isreal(rho_tilde[i+1]))
            if abs(rho_tilde[i]) < 1e-10:
                print "Warning2: scaling near-zero rho_tilde element to 1.0!"
                inv_delta0_diag[i] = 1e10 # ~= 1 / 1e-10
            else:
                inv_delta0_diag[i] = 1.0 / rho_tilde[i].real

            if abs(rho_tilde[i+1]) < 1e-10:
                print "Warning3: scaling near-zero rho_tilde element to 1.0!"
                inv_delta0_diag[i+1] = 1e10 # ~= 1 / 1e-10
            else:
                inv_delta0_diag[i+1] = 1.0 / rho_tilde[i].real

    if len(D0_params) % 2 == 1: #then there's an un-paired real eigenvalue
        i = len(D0_params)-1
        assert(_np.isreal(rho_tilde[i]))
        if abs(rho_tilde[i]) < 1e-10:
            print "Warning4: scaling near-zero rho_tilde element to 1.0!"
            inv_delta0_diag[i] = 1e10 # ~= 1 / 1e-10
        else:
            inv_delta0_diag[i] = 1.0 / rho_tilde[i].real

    return 1.0 / inv_delta0_diag # delta0_diag (could compute directly above?)


def _get_ET_params(ET_tilde, D0_params):
    # ET_tilde is a (complex) row-vector with conjugate-pair structure given
    # by D0_params
    ET_tilde = ET_tilde.flatten() #so we can index using a single index
    E_params = _np.empty(len(ET_tilde),'d') #Note: *not* complex

    for i in range(0,len(D0_params)-1,2):
        a,b = D0_params[i:i+2]
        if b <= 0:
            # complex-conj pair at index i,i+1, so:
            assert(_np.isclose(ET_tilde[i],ET_tilde[i+1].conj()))
            E_params[i] = ET_tilde[i].real
            E_params[i+1] = ET_tilde[i].imag # (can be pos or neg)
            #TODO: maybe we divide by abs(b) before setting E_params??
        else:
            # real pair at index i,i+1, so:
            assert(_np.isreal(ET_tilde[i]) and _np.isreal(ET_tilde[i+1]))
            E_params[i]   = (ET_tilde[i].real + ET_tilde[i+1].real)/2.0
            E_params[i+1] = (ET_tilde[i].real - ET_tilde[i+1].real)/2.0
            #TODO: maybe we divide by abs(b) before setting E_params??

    if len(D0_params) % 2 == 1: #then there's an un-paired real eigenvalue
        i = len(D0_params)-1
        assert(_np.isreal(ET_tilde[i]))
        E_params[i] = ET_tilde[i].real

    return E_params


def _get_B_params(invYjY0, Dj_params, D0_params):
    #Need to find inv(deltaj) to fix diagonal els (==1) of 
    # B0j == inv(deltaj) * invYjY0  (j != 0)
    # where invYjY0 has special "two-sided" (rows+cols) conjugacy structure
    # given by Dj_params (rows) and D0_params (cols).  Diagonal els of 
    # inv(deltaj) will have conjugacy-pair structure of Dj_params so overall
    # structure of B0j is the same as that of invYjY0.  After deltaj element
    # are found, conjugacy-pair structure is used to extract (real) parameters
    # of B0j.

    assert(len(Dj_params) == len(D0_params))
    inv_deltaj_diag = _np.empty(invYjY0.shape[0],'complex')

    for i in range(0,len(Dj_params)-1,2):
        a1,b1 = Dj_params[i:i+2] #rows
        a2,b2 = D0_params[i:i+2] #cols
        if b1 <= 0:
            # complex-conj pair rows at index i,i+1
            if abs(invYjY0[i,i]) < 1e-10:
                print "Warning: scaling near-zero B0j element to 1.0!"
                inv_deltaj_diag[i] = 1e10 # ~= 1 / 1e-10
            else:
                inv_deltaj_diag[i] = 1.0 / invYjY0[i,i] # complex division
            inv_deltaj_diag[i+1] = inv_deltaj_diag[i].conj()

            if b2 <= 0:
                # complex-conj pair rows & cols at index i,i+1,
                # so deltaj computed above scales both diagonal els to 1
                # (they're complex conjugates of each other)
                assert(_np.isclose(invYjY0[i,i],invYjY0[i+1,i+1].conj()))
                assert(_np.isclose(invYjY0[i+1,i], invYjY0[i,i+1].conj()))
            else:
                # complex-conj pair rows & real-pair cols at index i,i+1,
                # so deltaj computed above scales [i,i], and [i+1,i] els to 1
                # (they're complex conjugates of each other)
                assert(_np.isclose(invYjY0[i,i], invYjY0[i+1,i].conj()))
                assert(_np.isclose(invYjY0[i,i+1], invYjY0[i+1,i+1].conj()))

        else:
            # real-pair rows at index i,i+1
            if abs(invYjY0[i,i]) < 1e-10:
                print "Warning: scaling near-zero B0j element to 1.0!"
                inv_deltaj_diag[i] = 1e10 # ~= 1 / 1e-10
            else:
                inv_deltaj_diag[i] = 1.0 / invYjY0[i,i].real

            if abs(invYjY0[i+1,i+1]) < 1e-10:
                print "Warning: scaling near-zero B0j element to 1.0!"
                inv_deltaj_diag[i+1] = 1e10 # ~= 1 / 1e-10
            else:
                inv_deltaj_diag[i+1] = 1.0 / invYjY0[i+1,i+1].real

            if b2 <= 0:
                # real-pair rows & complex-conj pair cols at index i,i+1,
                # so deltaj computed above scales the *real* part of both
                # diagonal els to 1 (and thereby the real parts of all
                # four of [i,i], [i,i+1], [i+1,i], [i+1,i+1] b/c:
                assert(_np.isclose(invYjY0[i,i], invYjY0[i,i+1].conj()))
                assert(_np.isclose(invYjY0[i+1,i], invYjY0[i+1,i+1].conj()))
            else:
                # real-pair rows & cols at index i,i+1, so deltaj
                # computed above scales both (real) diagonal els to 1
                assert(_np.isreal(invYjY0[i,i]) and 
                       _np.isreal(invYjY0[i+1,i+1]))


    if len(Dj_params) % 2 == 1: #then there's an un-paired real eigenvalue
        i = len(Dj_params)-1
        assert(_np.isreal(invYjY0[i,i]))
        if abs(invYjY0[i,i]) < 1e-10:
            print "Warning: scaling near-zero B0j element to 1.0!"
            inv_deltaj_diag[i] = 1e10 # ~= 1 / 1e-10
        else:
            inv_deltaj_diag[i] = 1.0 / invYjY0[i,i].real
        #scaling sets diagonal element to 1

    # Scale invYjY0
    B0j = _np.dot( _np.diag(inv_deltaj_diag), invYjY0 )
    
    # Extract (real) parameters from B0j
    B0j_params = {} # a dictionary of lists, indexed by two "2x2 block" indices
    for i in range(0,len(Dj_params)-1,2): #loop over row-pairs
        a1,b1 = Dj_params[i:i+2] #rows
        for j in range(0,len(D0_params)-1,2): #loop over col-pairs
            a2,b2 = D0_params[i:i+2] #cols

            #Each 2x2 square of B0j contains 4 real parameters (after
            # accounting for structure) *except* if i == j, in which case
            # the deltaj-scaling has removed two of these, leaving only 2.
            if b1 <= 0:
                if b2 <= 0:
                    # complex-conj pair rows & cols, so
                    # block is [ [a, b], [b.C, a.C] ]; parameterize a then b.
                    assert(_np.isclose(B0j[i,j], B0j[i+1,j+1].conj()))
                    assert(_np.isclose(B0j[i+1,j], B0j[i,j+1].conj()))
                else:
                    # complex-conj pair rows & real-pair cols, so
                    # block is [ [a, b], [a.C, b.C] ]; parameterize a then b.
                    assert(_np.isclose(B0j[i,j], B0j[i+1,j].conj()))
                    assert(_np.isclose(B0j[i,j+1], B0j[i+1,j+1].conj()))

                #NOTE: since both cases above do exacty the same thing (because
                # a and b lie in the same positions ([i,i] and [i,i+1]) )
                # there's no need to put the code below into the b2 if blocks.
                if i != j:
                    B0j_params[i//2,j//2] = \
                        [ B0j[i,j].real, B0j[i,j].imag,
                          B0j[i,j+1].real, B0j[i,j+1].imag ]
                else: # a == 1, so just parameterize b
                    assert( _np.isclose(B0j[i,j],1.0) )
                    B0j_params[i//2,j//2] = \
                        [ B0j[i,j+1].real, B0j[i,j+1].imag ]
                #TODO: maybe we divide by abs(b) before setting??
    
            else:
                if b2 <= 0:
                    # real-pair rows & complex-conj pair cols,
                    # so block is [ [a, a.C], [b, b.C] ]; parameterize a then b.
                    assert(_np.isclose(B0j[i,j], B0j[i,j+1].conj()))
                    assert(_np.isclose(B0j[i+1,j], B0j[i+1,j+1].conj()))

                    if i != j:
                        B0j_params[i//2,j//2] = \
                            [ B0j[i,j].real, B0j[i,j].imag,
                              B0j[i+1,j].real, B0j[i+1,j].imag ]
                    else: # a.real == b.real == 1, so just parameterize imag
                        assert( _np.isclose(B0j[i,j].real,1.0) and
                                _np.isclose(B0j[i+1,j].real,1.0) )
                        B0j_params[i//2,j//2] = \
                            [ B0j[i,j].imag, B0j[i+1,j].imag ]
                    #TODO: maybe we divide by abs(b) before setting??

                else:
                    # real-pair rows & cols, so block is
                    # [ [a, b], [c, d] ] (all real); parameterize a, b, c, d.
                    assert(_np.isreal(B0j[i,j]) and _np.isreal(B0j[i,j+1]) and 
                           _np.isreal(B0j[i+1,j]) and _np.isreal(B0j[i+1,j+1]))

                    if i != j:
                        B0j_params[i//2,j//2] = \
                            [ B0j[i,j].real, B0j[i,j+1].real,
                              B0j[i+1,j].real, B0j[i+1,j+1].real ]
                    else: # a == d == 1, so just parameterize b, c
                        assert( _np.isclose(B0j[i,j],1.0) )
                        B0j_params[i//2,j//2] = \
                            [ B0j[i,j+1].real, B0j[i+1,j].real ]
                    #TODO: maybe we divide by abs(b) before setting??

    if len(Dj_params) % 2 == 1: #then there's an un-paired real eigenvalue
        M = len(Dj_params)//2 # index of unpaired block in B0j_params
        i = len(Dj_params)-1
        for j in range(0,len(D0_params)-1,2): #loop over col-pairs (final row)
            a2,b2 = D0_params[i:i+2] #cols
            
            if b2 <= 0:
                # single-real row & complex-conj pair cols,
                # so block is [a, a.C]; parameterize a
                # (note i can never equal j)
                assert(_np.isclose(B0j[i,j], B0j[i,j+1].conj()))
                B0j_params[M,j//2] = \
                    [ B0j[i,j].real, B0j[i,j].imag ]
                #TODO: maybe we divide by abs(b) before setting??

            else:
                # single-real row & real-pair cols, so block is
                # [a, b] (both real); parameterize a, b
                assert(_np.isreal(B0j[i,j]) and _np.isreal(B0j[i,j+1]))
                B0j_params[M,j//2] = \
                    [ B0j[i,j].real, B0j[i,j+1].real ]
                #TODO: maybe we divide by abs(b) before setting??

        j = len(D0_params)-1
        assert(j == i) #since D?_params are the same length
        for i in range(0,len(Dj_params)-1,2): #loop over row-pairs (final col)
            a1,b1 = Dj_params[i:i+2] #cols
            
            if b1 <= 0:
                # complex-conj pair rows & single-real col,
                # so block is [[a], [a.C]]; parameterize a
                # (note i can never equal j)
                assert(_np.isclose(B0j[i,j], B0j[i+1,j].conj()))
                B0j_params[i//2,M] = \
                    [ B0j[i,j].real, B0j[i,j].imag ]
                #TODO: maybe we divide by abs(b) before setting??

            else:
                # real-pair rows & single-real col, so block is
                # [[a], [b]] (both real); parameterize a, b
                assert(_np.isreal(B0j[i,j]) and _np.isreal(B0j[i+1,j]))
                B0j_params[i//2,M] = \
                    [ B0j[i,j].real, B0j[i+1,j].real ]
                #TODO: maybe we divide by abs(b) before setting??

        #Now deal with final diagonal element (single real row & col). The
        # deltaj scaling has set this element to 1, so no more parameters
        # are needed.
        assert( _np.isclose(B0j[j,j], 1.0) )
        #B0j_params[M,M] = [ ] # just so this list exists for loop below?
    else:
        M = None #there is no unpaired block, so no index for it!

    #Now collect B0j_params into a numpy array by concatenating blocks.
    # (This always puts the diagonal blocks into the same locations, so
    #  there's no ambiguity about the size of each segment)
    concat_params = []
    n2x2 = len(Dj_params)//2 # number of 2x2 blocks
    for k in range(n2x2):
        for l in range(n2x2):
            if k == l: assert(len(B0j_params[k,l]) == 2)
            else: assert(len(B0j_params[k,l]) == 4)
            concat_params.extend( B0j_params[k,l] )

    if len(Dj_params) % 2 == 1: #then there's an un-paired eigenvalue
        #Add final row
        for l in range(n2x2):
            assert(len(B0j_params[M,l]) == 2)
            concat_params.extend( B0j_params[M,l] )

        #Add final col
        for k in range(n2x2):
            assert(len(B0j_params[k,M]) == 2)
            concat_params.extend( B0j_params[k,M] )
            
    assert( all(_np.isreal(concat_params)) )
    return _np.array(concat_params, 'd')
        

def _constructDj(Dj_params):
    #Construct Dj
    Dj_diag = _np.empty( len(Dj_params), 'complex' )
    for i in range(0,len(Dj_params)-1,2):    
        a,b = Dj_params[i:i+2]
        if b <= 0: # complex-conj pair
            Dj_diag[i]   = a-b*1j #a + abs(b)*1j
            Dj_diag[i+1] = a+b*1j #a - abs(b)*1j
        else: # real-pair
            Dj_diag[i]   = a+b
            Dj_diag[i+1] = a-b
    if len(Dj_params) % 2 == 1: # un-paired real eigenvalue
        Dj_diag[-1] = Dj_params[-1]
    return _np.diag(Dj_diag)
    


def _deparameterize_real_gate_mx(Dj_params, D0_params, B0j_params,
                                 Y0, verbosity):
    assert(len(Dj_params) == len(D0_params))

    #Construct Dj
    Dj = _constructDj(Dj_params)

    #Construct Yj, inv(Yj)
    # B0j := inv(Yj)Y0, so deparameterize B0j then apply inv(Y0)
    B0j = _np.empty( (len(Dj_params),len(Dj_params)), 'complex' )
    
    # Extract (real) parameters from B0j
    #B0j_params = {} # a dictionary of lists, indexed by two "2x2 block" indices
    #M = len(Dj_params)//2 #maximum 2x2 block index

    k = 0 #running index into B0j_params
    for i in range(0,len(Dj_params)-1,2): #loop over row-pairs
        a1,b1 = Dj_params[i:i+2] #rows
        for j in range(0,len(D0_params)-1,2): #loop over col-pairs
            a2,b2 = D0_params[i:i+2] #cols

            #Each 2x2 square of B0j is specified with 4 real parameters
            # *except* if i == j, in which case our deltaj-scaling has
            # removed two of these, leaving only 2.
            nP = 2 if (i == j) else 4
            params = B0j_params[k:k+nP]
            k += nP

            if b1 <= 0:

                #Get parameters of 2x2 block (which we call a and b below)
                if i == j: #just b parameterized (either case, a is scaled to 1)
                    ar,ai = 1.0, 0
                    br,bi = params
                else: # a then b parameterized
                    ar,ai,br,bi = params

                if b2 <= 0:
                    # complex-conj pair rows & cols, so
                    # block is [ [a, b], [b.C, a.C] ]
                    B0j[i,j]     = ar + ai*1j
                    B0j[i,j+1]   = br + bi*1j
                    B0j[i+1,j]   = br - bi*1j
                    B0j[i+1,j+1] = ar - ai*1j
                else:
                    # complex-conj pair rows & real-pair cols, so
                    # block is [ [a, b], [a.C, b.C] ]
                    B0j[i,j]     = ar + ai*1j
                    B0j[i,j+1]   = br + bi*1j
                    B0j[i+1,j]   = ar - ai*1j
                    B0j[i+1,j+1] = br - bi*1j
    
            else:
                if b2 <= 0:
                    # real-pair rows & complex-conj pair cols,
                    # so block is [ [a, a.C], [b, b.C] ]

                    #Get parameters of 2x2 block (a and b)
                    if i == j: #a.real, b.real scaled to 1, just imag a,b
                        ar,br = 1.0, 1.0
                        ai,bi = params
                    else: # a then b parameterized
                        ar,ai,br,bi = params

                    B0j[i,j]     = ar + ai*1j
                    B0j[i,j+1]   = ar - ai*1j
                    B0j[i+1,j]   = br + bi*1j
                    B0j[i+1,j+1] = br - bi*1j
                    #TODO: maybe we divide by abs(b) before setting??

                else:
                    # real-pair rows & cols, so block is
                    # [ [a, b], [c, d] ] (all real)

                    #Get parameters of 2x2 block (a, b, c, d)
                    if i == j: # a == d == 1, so just b, c
                        a,d = 1.0, 1.0
                        b,c = params
                    else: # a, b, c, d parameterized
                        a,b,c,d = params

                    B0j[i,j]     = a
                    B0j[i,j+1]   = b
                    B0j[i+1,j]   = c
                    B0j[i+1,j+1] = d
                    #TODO: maybe we divide by abs(b) before setting??

    if len(Dj_params) % 2 == 1: #then there's an un-paired real eigenvalue
        i = len(Dj_params)-1
        for j in range(0,len(D0_params)-1,2): #loop over col-pairs
            a2,b2 = D0_params[i:i+2] #cols
            params = B0j_params[k:k+2]; k += 2 #always length 2 (i != j always)

            if b2 <= 0:
                # single-real row & complex-conj pair cols,
                # so block is [a, a.C]
                ar,ai = params
                B0j[i,j]   = a + ai*1j
                B0j[i,j+1] = a - ai*1j
                #TODO: maybe we divide by abs(b) before setting??

            else:
                # single-real row & real-pair cols, so block is
                # [a, b] (both real)
                a,b = params
                B0j[i,j]   = a
                B0j[i,j+1] = b
                #TODO: maybe we divide by abs(b) before setting??


        j = len(D0_params)-1
        assert(j == i) #since D?_params are the same length
        for i in range(0,len(Dj_params)-1,2): #loop over row-pairs (final col)
            a1,b1 = Dj_params[i:i+2] #cols
            params = B0j_params[k:k+2]; k += 2 #always length 2 (i != j always)
            
            if b1 <= 0:
                # complex-conj pair rows & single-real col,
                # so block is [[a], [a.C]]
                ar,ai = params
                B0j[i,j]   = a + ai*1j
                B0j[i+1,j] = a - ai*1j
                #TODO: maybe we divide by abs(b) before setting??

            else:
                # real-pair rows & single-real col, so block is
                # [[a], [b]] (both real)
                a,b = params
                B0j[i,j]   = a
                B0j[i+1,j] = b
                #TODO: maybe we divide by abs(b) before setting??

        #Now deal with final diagonal element (single real row & col). The
        # deltaj scaling has set this element to 1, so set:
        B0j[j,j] = 1.0

    invYj = _np.dot( B0j, _np.linalg.inv(Y0)) # b/c B0j = inv(Yj)Y0
    Yj = _np.linalg.inv(invYj)

    if verbosity > 3:
        print "De-parameterizing gate:"
        print "Yj = ";_mt.print_mx(Yj)
        print "invYj = ";_mt.print_mx(invYj)
        print "Dj = ";_mt.print_mx(Dj)
        print "mx = ";_mt.print_mx( _np.dot(Yj, _np.dot(Dj, invYj)))

    #Construct gate
    mx = _np.dot(Yj, _np.dot(Dj, invYj))    
    assert(all(_np.isreal(mx.flatten())))

    return _np.real(mx)


def _get_ETilde_vector( E_params, D0_params ):
    E_tilde = _np.empty( (len(E_params),1),'complex')

    for i in range(0,len(D0_params)-1,2):
        a,b = D0_params[i:i+2]
        if b <= 0:
            # complex-conj pair at index i,i+1, so:
            Er,Ei = E_params[i:i+2]
            E_tilde[i]   = Er + Ei*1j
            E_tilde[i+1] = Er - Ei*1j
            #TODO: maybe we divide by abs(b) before setting E_params??
        else:
            # real pair at index i,i+1, so:
            E1,E2 = E_params[i:i+2]
            E_tilde[i]   = E1 + E2
            E_tilde[i+1] = E1 - E2
            #TODO: maybe we divide by abs(b) before setting E_params??

    if len(D0_params) % 2 == 1: #then there's an un-paired real eigenvalue
        E_tilde[len(D0_params)-1] = E_params[len(D0_params)-1]

    return E_tilde
