from __future__ import division, print_function, absolute_import, unicode_literals
#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************
"""
Functions which compute named quantities for GateSets and Datasets.

Named quantities as well as their confidence-region error bars are
 computed by the functions in this module. These quantities are
 used primarily in reports, so we refer to these quantities as
 "reportables".
"""
import numpy as _np
import scipy.linalg as _spl
import warnings as _warnings
from collections import OrderedDict as _OrderedDict

from .. import tools as _tools
from .. import algorithms as _alg
from ..objects import smart_cached as _smart_cached
from ..objects.reportableqty import ReportableQty as _ReportableQty
from ..objects import gatesetfunction as _gsf

import functools as _functools

from pprint import pprint

FINITE_DIFF_EPS = 1e-7

def _projectToValidProb(p, tol=1e-9):
    if p < tol: return tol
    if p > 1-tol: return 1-tol
    return p

def _make_reportable_qty_or_dict(f0, df=None, nonMarkovianEBs=False):
    """ Just adds special processing with f0 is a dict, where we 
        return a dict or ReportableQtys rather than a single
        ReportableQty of the dict.
    """
    if isinstance(f0,dict):
        #special processing for dict -> df is dict of error bars
        # and we return a dict of ReportableQtys
        if df:
            return { ky: _ReportableQty(f0[ky], df[ky], nonMarkovianEBs) for ky in f0 }
        else:
            return { ky: _ReportableQty(f0[ky], None, False) for ky in f0 }
    else:
        return _ReportableQty(f0, df, nonMarkovianEBs)

def evaluate(gatesetFn, cri=None, verbosity=0):
    if gatesetFn is None: # so you can set fn to None when they're missing (e.g. diamond norm)
        return _ReportableQty(_np.nan)
    
    if cri:
        nmEBs = bool(cri.get_errobar_type() == "non-markovian")
        df, f0 =  cri.get_fn_confidence_interval(
            gatesetFn, returnFnVal=True,
            verbosity=verbosity)
        return _make_reportable_qty_or_dict(f0, df, nmEBs)
    else:
        return _make_reportable_qty_or_dict( gatesetFn.evaluate(gatesetFn.base_gateset) )


def spam_dotprods(rhoVecs, EVecs):
    ret = _np.empty( (len(rhoVecs), len(EVecs)), 'd')
    for i,rhoVec in enumerate(rhoVecs):
        for j,EVec in enumerate(EVecs):
            ret[i,j] = _np.dot(_np.transpose(EVec), rhoVec)
    return ret
Spam_dotprods = _gsf.spamfn_factory(spam_dotprods) #init args == (gateset)


def choi_matrix(gate, mxBasis):
    return _tools.jamiolkowski_iso(gate, mxBasis, mxBasis)
Choi_matrix = _gsf.gatefn_factory(choi_matrix) # init args == (gateset, gateLabel)


def choi_evals(gate, mxBasis):
    choi = _tools.jamiolkowski_iso(gate, mxBasis, mxBasis)
    choi_eigvals = _np.linalg.eigvals(choi)
    return _np.array(sorted(choi_eigvals))
Choi_evals = _gsf.gatefn_factory(choi_evals) # init args == (gateset, gateLabel)


def choi_trace(gate, mxBasis):
    choi = _tools.jamiolkowski_iso(gate, mxBasis, mxBasis)
    return _np.trace(choi)
Choi_trace = _gsf.gatefn_factory(choi_trace) # init args == (gateset, gateLabel)



class Gate_eigenvalues(_gsf.GateSetFunction):
    def __init__(self, gateset, gatelabel):
        self.gatelabel = gatelabel
        _gsf.GateSetFunction.__init__(self, gateset, ["gate:" + gatelabel])
            
    def evaluate(self, gateset):
        evals,evecs = _np.linalg.eig(gateset.gates[self.gatelabel])
        
        ev_list = list(enumerate(evals))
        ev_list.sort(key=lambda tup:abs(tup[1]), reverse=True)
        indx,evals = zip(*ev_list)
        evecs = evecs[:,indx] #sort evecs according to evals

        self.G0 = gateset.gates[self.gatelabel]
        self.evals = _np.array(evals)
        self.evecs = evecs
        self.inv_evecs = _np.linalg.inv(evecs)

        return self.evals

    def evaluate_nearby(self, nearby_gateset):
        #avoid calling minweight_match again
        dMx = nearby_gateset.gates[self.gatelabel] - self.G0
        #evalsM = evals0 + Uinv * (M-M0) * U
        return _np.array( [ self.evals[k] + _np.dot(self.inv_evecs[k,:], _np.dot(dMx, self.evecs[:,k]))
                            for k in range(dMx.shape[0])] )
    # ref for eigenvalue derivatives: https://www.win.tue.nl/casa/meetings/seminar/previous/_abstract051019_files/Presentation.pdf


#def gate_eigenvalues(gate, mxBasis):
#    return _np.array(sorted(_np.linalg.eigvals(gate),
#                            key=lambda ev: abs(ev), reverse=True))
#Gate_eigenvalues = _gsf.gatefn_factory(gate_eigenvalues)
## init args == (gateset, gateLabel)


#Example....
#class Gatestring_eigenvalues(_gsf.GateSetFunction):
#    def __init__(self, gatesetA, gatesetB, gatestring):
#        self.gatestring = gatestring
#        self.B = gatesetB.product(gatestring)
#        self.evB = _np.linalg.eigvals(B)
#        self.gatestring = gatestring
#        _gsf.GateSetFunction.__init__(self, gatesetA, ["all"])
#            
#    def evaluate(self, gateset):
#        Mx = gateset.product(self.gatestring)
#        return _np.array(sorted(_np.linalg.eigvals(),
#                            key=lambda ev: abs(ev), reverse=True))
#
#        A = gateset.product(self.gatestring)
#        evA, evecsA = _np.linalg.eig(A)
#        self.A0, self.evA0, self.evecsA0, self.ievecsA0 = A, evA, evecsA, _np.linalg.inv(evecsA) #save for evaluate_nearby...
#        wts, self.pairs = _tools.minweight_match(evA, self.evB, lambda x,y: abs(x-y), return_pairs=True)
#        return _np.max(wts)
#
#    def evaluate_nearby(self, nearby_gateset):
#        #avoid calling minweight_match again
#        A = nearby_gateset.product(self.gatestring)
#        dA = A - self.A0
#        #evA = _np.linalg.eigvals(A)  # = self.evA0 + U * (A-A0) * Udag
#        evA = _np.array( [ self.evA0 + _np.dot(self.ievecsA0[k,:], _np.dot(dA, self.evecsA0[:,k])) for k in range(dA.shape[0])] )
#        return _np.max( [ abs(evA[i]-self.evB[j]) for i,j in self.pairs ] )


class Gatestring_eigenvalues(_gsf.GateSetFunction):
    def __init__(self, gateset, gatestring):
        self.gatestring = gatestring
        _gsf.GateSetFunction.__init__(self, gateset, ["all"])
            
    def evaluate(self, gateset):
        Mx = gateset.product(self.gatestring)
        evals,evecs = _np.linalg.eig(Mx)
        
        ev_list = list(enumerate(evals))
        ev_list.sort(key=lambda tup:abs(tup[1]), reverse=True)
        indx,evals = zip(*ev_list)
        evecs = evecs[:,indx] #sort evecs according to evals

        self.Mx = Mx
        self.evals = _np.array(evals)
        self.evecs = evecs
        self.inv_evecs = _np.linalg.inv(evecs)

        return self.evals

    def evaluate_nearby(self, nearby_gateset):
        #avoid calling minweight_match again
        Mx = nearby_gateset.product(self.gatestring)
        dMx = Mx - self.Mx
        #evalsM = evals0 + Uinv * (M-M0) * U
        return _np.array( [ self.evals[k] + _np.dot(self.inv_evecs[k,:], _np.dot(dMx, self.evecs[:,k]))
                            for k in range(dMx.shape[0])] )
    # ref for eigenvalue derivatives: https://www.win.tue.nl/casa/meetings/seminar/previous/_abstract051019_files/Presentation.pdf


#def gatestring_eigenvalues(gateset, gatestring):
#    return _np.array(sorted(_np.linalg.eigvals(gateset.product(gatestring)),
#                            key=lambda ev: abs(ev), reverse=True))
#Gatestring_eigenvalues = _gsf.gatesetfn_factory(gatestring_eigenvalues)
## init args == (gateset, gatestring)

  
def rel_gatestring_eigenvalues(gatesetA, gatesetB, gatestring):
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    rel_gate = _np.dot(_np.linalg.inv(B), A) # "relative gate" == target^{-1} * gate
    return _np.linalg.eigvals(rel_gate)
Rel_gatestring_eigenvalues = _gsf.gatesetfn_factory(rel_gatestring_eigenvalues)
# init args == (gatesetA, gatesetB, gatestring) 


def gatestring_fro_diff(gatesetA, gatesetB, gatestring):
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    return fro_diff(A,B,gatesetB.basis)
Gatestring_fro_diff = _gsf.gatesetfn_factory(gatestring_fro_diff)
# init args == (gatesetA, gatesetB, gatestring)

def gatestring_entanglement_infidelity(gatesetA, gatesetB, gatestring):
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    return entanglement_infidelity(A,B,gatesetB.basis)
Gatestring_entanglement_infidelity = _gsf.gatesetfn_factory(gatestring_entanglement_infidelity)
# init args == (gatesetA, gatesetB, gatestring)

def gatestring_avg_gate_infidelity(gatesetA, gatesetB, gatestring):
    """ Returns the average gate infidelity between A and B, where B is the "target" operation."""
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    return avg_gate_infidelity(A,B,gatesetB.basis)
Gatestring_avg_gate_infidelity = _gsf.gatesetfn_factory(gatestring_avg_gate_infidelity)
  # init args == (gatesetA, gatesetB, gatestring)


def gatestring_jt_diff(gatesetA, gatesetB, gatestring):
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    return jt_diff(A, B, gatesetB.basis)
Gatestring_jt_diff = _gsf.gatesetfn_factory(gatestring_jt_diff)
# init args == (gatesetA, gatesetB, gatestring)

try:
    import cvxpy as _cvxpy

    class Gatestring_half_diamond_norm(_gsf.GateSetFunction):
        def __init__(self, gatesetA, gatesetB, gatestring):
            self.gatestring = gatestring
            self.B = gatesetB.product(gatestring)
            self.d = int(round(_np.sqrt(gatesetA.dim)))
            _gsf.GateSetFunction.__init__(self, gatesetA, ["all"])
                
        def evaluate(self, gateset):
            A = gateset.product(self.gatestring)
            dm, W = _tools.diamonddist(A, self.B, gateset.basis,
                                       return_x=True)
            self.W = W
            return 0.5*dm
    
        def evaluate_nearby(self, nearby_gateset):
            mxBasis = nearby_gateset.basis
            JAstd = self.d * _tools.fast_jamiolkowski_iso_std(
                nearby_gateset.product(self.gatestring), mxBasis)
            JBstd = self.d * _tools.fast_jamiolkowski_iso_std(self.B, mxBasis)
            Jt = (JBstd-JAstd).T
            return 0.5*_np.trace( Jt.real * self.W.real + Jt.imag * self.W.imag)

    #def gatestring_half_diamond_norm(gatesetA, gatesetB, gatestring):
    #    A = gatesetA.product(gatestring) # "gate"
    #    B = gatesetB.product(gatestring) # "target gate"
    #    return half_diamond_norm(A, B, gatesetB.basis)
    #Gatestring_half_diamond_norm = _gsf.gatesetfn_factory(gatestring_half_diamond_norm)
    #  # init args == (gatesetA, gatesetB, gatestring)

except ImportError:
    gatestring_half_diamond_norm = None
    Gatestring_half_diamond_norm = None


def gatestring_nonunitary_entanglement_infidelity(gatesetA, gatesetB, gatestring):
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    return nonunitary_entanglement_infidelity(A,B,gatesetB.basis)
Gatestring_nonunitary_entanglement_infidelity = _gsf.gatesetfn_factory(gatestring_nonunitary_entanglement_infidelity)
  # init args == (gatesetA, gatesetB, gatestring)


def gatestring_nonunitary_avg_gate_infidelity(gatesetA, gatesetB, gatestring):
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    return nonunitary_avg_gate_infidelity(A,B,gatesetB.basis)
Gatestring_nonunitary_avg_gate_infidelity = _gsf.gatesetfn_factory(gatestring_nonunitary_avg_gate_infidelity)
  # init args == (gatesetA, gatesetB, gatestring)


def gatestring_eigenvalue_entanglement_infidelity(gatesetA, gatesetB, gatestring):
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    return eigenvalue_entanglement_infidelity(A,B,gatesetB.basis)
Gatestring_eigenvalue_entanglement_infidelity = _gsf.gatesetfn_factory(gatestring_eigenvalue_entanglement_infidelity)
  # init args == (gatesetA, gatesetB, gatestring)


def gatestring_eigenvalue_avg_gate_infidelity(gatesetA, gatesetB, gatestring):
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    return eigenvalue_avg_gate_infidelity(A,B,gatesetB.basis)
Gatestring_eigenvalue_avg_gate_infidelity = _gsf.gatesetfn_factory(gatestring_eigenvalue_avg_gate_infidelity)
  # init args == (gatesetA, gatesetB, gatestring)

def gatestring_eigenvalue_nonunitary_entanglement_infidelity(gatesetA, gatesetB, gatestring):
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    return eigenvalue_nonunitary_entanglement_infidelity(A,B,gatesetB.basis)
Gatestring_eigenvalue_nonunitary_entanglement_infidelity = _gsf.gatesetfn_factory(gatestring_eigenvalue_nonunitary_entanglement_infidelity)
  # init args == (gatesetA, gatesetB, gatestring)


def gatestring_eigenvalue_nonunitary_avg_gate_infidelity(gatesetA, gatesetB, gatestring):
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    return eigenvalue_nonunitary_avg_gate_infidelity(A,B,gatesetB.basis)
Gatestring_eigenvalue_nonunitary_avg_gate_infidelity = _gsf.gatesetfn_factory(gatestring_eigenvalue_nonunitary_avg_gate_infidelity)
  # init args == (gatesetA, gatesetB, gatestring)

  
def gatestring_eigenvalue_diamondnorm(gatesetA, gatesetB, gatestring):
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    return eigenvalue_diamondnorm(A,B,gatesetB.basis)
Gatestring_eigenvalue_diamondnorm = _gsf.gatesetfn_factory(gatestring_eigenvalue_diamondnorm)
# init args == (gatesetA, gatesetB, gatestring)


def gatestring_eigenvalue_nonunitary_diamondnorm(gatesetA, gatesetB, gatestring):
    A = gatesetA.product(gatestring) # "gate"
    B = gatesetB.product(gatestring) # "target gate"
    return eigenvalue_nonunitary_diamondnorm(A,B,gatesetB.basis)
Gatestring_eigenvalue_nonunitary_diamondnorm = _gsf.gatesetfn_factory(gatestring_eigenvalue_nonunitary_diamondnorm)
# init args == (gatesetA, gatesetB, gatestring)


def povm_entanglement_infidelity(gatesetA, gatesetB):
    return 1.0 - _tools.povm_fidelity(gatesetA, gatesetB)
POVM_entanglement_infidelity = _gsf.povmfn_factory(povm_entanglement_infidelity)

def povm_jt_diff(gatesetA, gatesetB):
    return _tools.povm_jtracedist(gatesetA, gatesetB)
POVM_jt_diff = _gsf.povmfn_factory(povm_jt_diff)

def povm_half_diamond_norm(gatesetA, gatesetB):
    return 0.5 * _tools.povm_diamonddist(gatesetA, gatesetB)
POVM_half_diamond_norm = _gsf.povmfn_factory(povm_half_diamond_norm)



def decomposition(gate):
    decompDict = _tools.decompose_gate_matrix(gate)
    if decompDict['isValid']:
        angleQty   = decompDict.get('pi rotations',0)
        diagQty    = decompDict.get('decay of diagonal rotation terms',0)
        offdiagQty = decompDict.get('decay of off diagonal rotation terms',0)
        errBarDict = { 'pi rotations': None,
                       'decay of diagonal rotation terms': None,
                       'decay of off diagonal rotation terms': None }
        return _ReportableQty(decompDict, errBarDict)
    else:
        return _ReportableQty({})

def upper_bound_fidelity(gate, mxBasis):
    return _tools.fidelity_upper_bound(gate)[0]
Upper_bound_fidelity = _gsf.gatefn_factory(upper_bound_fidelity)
# init args == (gateset, gateLabel)


def closest_ujmx(gate, mxBasis):
    closestUGateMx = _alg.find_closest_unitary_gatemx(gate)
    return _tools.jamiolkowski_iso(closestUGateMx, mxBasis, mxBasis)
Closest_ujmx = _gsf.gatefn_factory(closest_ujmx)
# init args == (gateset, gateLabel)


def maximum_fidelity(gate, mxBasis):
    closestUGateMx = _alg.find_closest_unitary_gatemx(gate)
    closestUJMx = _tools.jamiolkowski_iso(closestUGateMx, mxBasis, mxBasis)
    choi = _tools.jamiolkowski_iso(gate, mxBasis, mxBasis)
    return _tools.fidelity(closestUJMx, choi)
Maximum_fidelity = _gsf.gatefn_factory(maximum_fidelity)
# init args == (gateset, gateLabel)


def maximum_trace_dist(gate, mxBasis):
    closestUGateMx = _alg.find_closest_unitary_gatemx(gate)
    #closestUJMx = _tools.jamiolkowski_iso(closestUGateMx, mxBasis, mxBasis)
    _tools.jamiolkowski_iso(closestUGateMx, mxBasis, mxBasis)
    return _tools.jtracedist(gate, closestUGateMx)
Maximum_trace_dist = _gsf.gatefn_factory(maximum_trace_dist)
# init args == (gateset, gateLabel)


def angles_btwn_rotn_axes(gateset):
    gateLabels = list(gateset.gates.keys())
    angles_btwn_rotn_axes = _np.zeros( (len(gateLabels), len(gateLabels)), 'd' )

    for i,gl in enumerate(gateLabels):
        decomp = _tools.decompose_gate_matrix(gateset.gates[gl])
        rotnAngle = decomp.get('pi rotations','X')
        axisOfRotn = decomp.get('axis of rotation',None)

        for j,gl_other in enumerate(gateLabels[i+1:],start=i+1):
            decomp_other = _tools.decompose_gate_matrix(gateset.gates[gl_other])
            rotnAngle_other = decomp_other.get('pi rotations','X')

            if str(rotnAngle) == 'X' or abs(rotnAngle) < 1e-4 or \
               str(rotnAngle_other) == 'X' or abs(rotnAngle_other) < 1e-4:
                angles_btwn_rotn_axes[i,j] =  _np.nan
            else:
                axisOfRotn_other = decomp_other.get('axis of rotation',None)
                if axisOfRotn is not None and axisOfRotn_other is not None:
                    real_dot =  _np.clip( _np.real(_np.dot(axisOfRotn,axisOfRotn_other)), -1.0, 1.0)
                    angles_btwn_rotn_axes[i,j] = _np.arccos( real_dot ) / _np.pi
                else:
                    angles_btwn_rotn_axes[i,j] = _np.nan

            angles_btwn_rotn_axes[j,i] = angles_btwn_rotn_axes[i,j]
    return angles_btwn_rotn_axes
Angles_btwn_rotn_axes = _gsf.gatesetfn_factory(angles_btwn_rotn_axes)
# init args == (gateset)


def entanglement_fidelity(A, mxBasis, B):
    return _tools.process_fidelity(A, B, mxBasis)
Entanglement_fidelity = _gsf.gatesfn_factory(entanglement_fidelity)
# init args == (gateset1, gateset2, gateLabel)


def entanglement_infidelity(A, B, mxBasis):
    return 1 - _tools.process_fidelity(A, B, mxBasis)
Entanglement_infidelity = _gsf.gatesfn_factory(entanglement_infidelity)
# init args == (gateset1, gateset2, gateLabel)


def closest_unitary_fidelity(A, B, mxBasis): # assume vary gateset1, gateset2 fixed
    decomp1 = _tools.decompose_gate_matrix(A)
    decomp2 = _tools.decompose_gate_matrix(B)

    if decomp1['isUnitary']:
        closestUGateMx1 = A
    else: closestUGateMx1 = _alg.find_closest_unitary_gatemx(A)

    if decomp2['isUnitary']:
        closestUGateMx2 = B
    else: closestUGateMx2 = _alg.find_closest_unitary_gatemx(A)

    closeChoi1 = _tools.jamiolkowski_iso(closestUGateMx1)
    closeChoi2 = _tools.jamiolkowski_iso(closestUGateMx2)
    return _tools.fidelity(closeChoi1, closeChoi2)
Closest_unitary_fidelity = _gsf.gatesfn_factory(closest_unitary_fidelity)
# init args == (gateset1, gateset2, gateLabel)


def fro_diff(A, B, mxBasis): # assume vary gateset1, gateset2 fixed
    return _tools.frobeniusdist(A, B)
Fro_diff = _gsf.gatesfn_factory(fro_diff)
# init args == (gateset1, gateset2, gateLabel)


def jt_diff(A, B, mxBasis): # assume vary gateset1, gateset2 fixed
    return _tools.jtracedist(A, B, mxBasis)
Jt_diff = _gsf.gatesfn_factory(jt_diff)
# init args == (gateset1, gateset2, gateLabel)


try:
    import cvxpy as _cvxpy

    class Half_diamond_norm(_gsf.GateSetFunction):
        def __init__(self, gatesetA, gatesetB, gatelabel):
            self.gatelabel = gatelabel
            self.B = gatesetB.gates[gatelabel]
            self.d = int(round(_np.sqrt(gatesetA.dim)))
            _gsf.GateSetFunction.__init__(self, gatesetA, ["gate:"+gatelabel])
                
        def evaluate(self, gateset):
            gl = self.gatelabel
            dm, W = _tools.diamonddist(gateset.gates[gl], self.B, gateset.basis,
                                       return_x=True)
            self.W = W
            return 0.5*dm
    
        def evaluate_nearby(self, nearby_gateset):
            gl = self.gatelabel; mxBasis = nearby_gateset.basis
            JAstd = self.d * _tools.fast_jamiolkowski_iso_std(
                nearby_gateset.gates[gl], mxBasis)
            JBstd = self.d * _tools.fast_jamiolkowski_iso_std(self.B, mxBasis)
            Jt = (JBstd-JAstd).T
            return 0.5*_np.trace( Jt.real * self.W.real + Jt.imag * self.W.imag)

    #def half_diamond_norm(A, B, mxBasis):
    #    return 0.5 * _tools.diamonddist(A, B, mxBasis)
    #Half_diamond_norm = _gsf.gatesfn_factory(half_diamond_norm)
    ## init args == (gateset1, gateset2, gateLabel)

except ImportError:
    half_diamond_norm = None
    Half_diamond_norm = None


def std_unitarity(A,B, mxBasis):
    """ A gauge-invariant quantity that behaves like the unitarity """
    from ..extras.rb import rbutils as _rbutils
    Lambda = _np.dot(A, _np.linalg.inv(B))
    return _rbutils.unitarity( Lambda, mxBasis )

def eigenvalue_unitarity(A,B):
    """ A gauge-invariant quantity that behaves like the unitarity """
    Lambda = _np.dot(A, _np.linalg.inv(B))
    d2 = Lambda.shape[0]
    lmb = _np.linalg.eigvals(Lambda)
    return (_np.real(_np.vdot(lmb,lmb)) - 1.0) / (d2 - 1.0)
    
def nonunitary_entanglement_infidelity(A, B, mxBasis):
    """ Returns (d^2 - 1)/d^2 * (1 - sqrt(U)), where U is the unitarity of A*B^{-1} """
    d2 = A.shape[0]; U = std_unitarity(A,B,mxBasis)
    return (d2-1.0)/d2 * (1.0 - _np.sqrt(U))
Nonunitary_entanglement_infidelity = _gsf.gatesfn_factory(nonunitary_entanglement_infidelity)
# init args == (gateset1, gateset2, gateLabel)


def nonunitary_avg_gate_infidelity(A, B, mxBasis):
    """ Returns (d - 1)/d * (1 - sqrt(U)), where U is the unitarity of A*B^{-1} """
    d2 = A.shape[0]; d = int(round(_np.sqrt(d2)))
    U = std_unitarity(A,B,mxBasis)
    return (d-1.0)/d * (1.0 - _np.sqrt(U))
Nonunitary_avg_gate_infidelity = _gsf.gatesfn_factory(nonunitary_avg_gate_infidelity)


def eigenvalue_nonunitary_entanglement_infidelity(A, B, mxBasis):
    """ Returns (d^2 - 1)/d^2 * (1 - sqrt(U)), where U is the eigenvalue-unitarity of A*B^{-1} """
    d2 = A.shape[0]; U = eigenvalue_unitarity(A,B)
    return (d2-1.0)/d2 * (1.0 - _np.sqrt(U))
Eigenvalue_nonunitary_entanglement_infidelity = _gsf.gatesfn_factory(eigenvalue_nonunitary_entanglement_infidelity)
# init args == (gateset1, gateset2, gateLabel)


def eigenvalue_nonunitary_avg_gate_infidelity(A, B, mxBasis):
    """ Returns (d - 1)/d * (1 - sqrt(U)), where U is the eigenvalue-unitarity of A*B^{-1} """
    d2 = A.shape[0]; d = int(round(_np.sqrt(d2)))
    U = eigenvalue_unitarity(A,B)
    return (d-1.0)/d * (1.0 - _np.sqrt(U))
Eigenvalue_nonunitary_avg_gate_infidelity = _gsf.gatesfn_factory(eigenvalue_nonunitary_avg_gate_infidelity)


def eigenvalue_entanglement_infidelity(A, B, mxBasis):
    d2 = A.shape[0]
    evA = _np.linalg.eigvals(A)
    evB = _np.linalg.eigvals(B)
    mlPl = _np.sum(_tools.minweight_match(evA,evB, lambda x,y: -_np.abs(_np.conjugate(y)*x),
                                 return_pairs=False))
    return 1.0 + mlPl/float(d2)
Eigenvalue_entanglement_infidelity = _gsf.gatesfn_factory(eigenvalue_entanglement_infidelity)
# init args == (gateset1, gateset2, gateLabel)


def eigenvalue_avg_gate_infidelity(A, B, mxBasis):
    d2 = A.shape[0]; d = int(round(_np.sqrt(d2)))
    evA = _np.linalg.eigvals(A)
    evB = _np.linalg.eigvals(B)
    mlPl = _np.sum(_tools.minweight_match(evA,evB, lambda x,y: -_np.abs(_np.conjugate(y)*x),
                                 return_pairs=False))
    return (d2 + mlPl)/float(d*(d+1))
Eigenvalue_avg_gate_infidelity = _gsf.gatesfn_factory(eigenvalue_avg_gate_infidelity)
# init args == (gateset1, gateset2, gateLabel)


def eigenvalue_diamondnorm(A, B, mxBasis):
    d2 = A.shape[0]
    evA = _np.linalg.eigvals(A)
    evB = _np.linalg.eigvals(B)
    return (d2-1.0)/d2 * _np.max(_tools.minweight_match(evA,evB, lambda x,y: abs(x-y),
                                                        return_pairs=False))
Eigenvalue_diamondnorm = _gsf.gatesfn_factory(eigenvalue_diamondnorm)
# init args == (gateset1, gateset2, gateLabel)


def eigenvalue_nonunitary_diamondnorm(A, B, mxBasis):
    d2 = A.shape[0]
    evA = _np.linalg.eigvals(A)
    evB = _np.linalg.eigvals(B)
    return (d2-1.0)/d2 * _np.max(_tools.minweight_match(evA,evB, lambda x,y: abs(abs(x)-abs(y)),
                                                        return_pairs=False))
Eigenvalue_nonunitary_diamondnorm = _gsf.gatesfn_factory(eigenvalue_nonunitary_diamondnorm)
# init args == (gateset1, gateset2, gateLabel)




#OLD: TIMS FN... seems perhaps better motivated, but for now keep this simple and equal to gatestring_ version
#@gate_quantity() # This function changes arguments to (gateLabel, gateset, confidenceRegionInfo)
#def gaugeinv_infidelity(gate, mxBasis):
#    """ 
#    Returns gauge-invariant "version" of the unitary fidelity in which
#    the unitarity is replaced with the gauge-invariant quantity
#    `(lambda^dagger lambda - 1) / (d**2 - 1)`, where `lambda` is the spectrum 
#    of A, which equals the unitarity in at least one particular gauge.
#    """
#    d2 = gate.shape[0]
#    lmb = _np.linalg.eigvals(gate)
#    Uproxy = (_np.real(_np.vdot(lmb,lmb)) - 1.0) / (d2 - 1.0)
#    return 1.0 - _np.sqrt( Uproxy )

def avg_gate_infidelity(A, B, mxBasis):
    """ Returns the average gate infidelity between A and B, where B is the "target" operation."""
    d = _np.sqrt(A.shape[0])
    from ..extras.rb import rbutils as _rbutils
    return _rbutils.average_gate_infidelity(A,B, d, mxBasis)
Avg_gate_infidelity = _gsf.gatesfn_factory(avg_gate_infidelity)
# init args == (gateset1, gateset2, gateLabel)



def gateset_gateset_angles_btwn_axes(A, B, mxBasis): #Note: default 'gm' basis
    decomp = _tools.decompose_gate_matrix(A)
    decomp2 = _tools.decompose_gate_matrix(B)
    axisOfRotn = decomp.get('axis of rotation', None)
    rotnAngle = decomp.get('pi rotations','X')
    axisOfRotn2 = decomp2.get('axis of rotation', None)
    rotnAngle2 = decomp2.get('pi rotations','X')

    if rotnAngle == 'X' or abs(rotnAngle) < 1e-4 or \
       rotnAngle2 == 'X' or abs(rotnAngle2) < 1e-4:
        return _np.nan

    if axisOfRotn is None or axisOfRotn2 is None:
        return _np.nan

    real_dot =  _np.clip( _np.real(_np.dot(axisOfRotn, axisOfRotn2)), -1.0, 1.0)
    return _np.arccos( abs(real_dot) ) / _np.pi
      #Note: abs() allows axis to be off by 180 degrees -- if showing *angle* as
      #      well, must flip sign of angle of rotation if you allow axis to
      #      "reverse" by 180 degrees.

Gateset_gateset_angles_btwn_axes = _gsf.gatesfn_factory(gateset_gateset_angles_btwn_axes)
# init args == (gateset1, gateset2, gateLabel)


def rel_eigvals(A, B, mxBasis):
    target_gate_inv = _np.linalg.inv(B)
    rel_gate = _np.dot(target_gate_inv, A)
    return _np.linalg.eigvals(rel_gate).astype("complex") #since they generally *can* be complex
Rel_eigvals = _gsf.gatesfn_factory(rel_eigvals)
# init args == (gateset1, gateset2, gateLabel)

def rel_logTiG_eigvals(A, B, mxBasis):
    rel_gate = _tools.error_generator(A, B, "logTiG")
    return _np.linalg.eigvals(rel_gate).astype("complex") #since they generally *can* be complex
Rel_logTiG_eigvals = _gsf.gatesfn_factory(rel_logTiG_eigvals)
# init args == (gateset1, gateset2, gateLabel)

def rel_logGTi_eigvals(A, B, mxBasis):
    rel_gate = _tools.error_generator(A, B, "logGTi")
    return _np.linalg.eigvals(rel_gate).astype("complex") #since they generally *can* be complex
Rel_logGTi_eigvals = _gsf.gatesfn_factory(rel_logGTi_eigvals)
# init args == (gateset1, gateset2, gateLabel)

def rel_logGmlogT_eigvals(A, B, mxBasis):
    rel_gate = _tools.error_generator(A, B, "logG-logT")
    return _np.linalg.eigvals(rel_gate).astype("complex") #since they generally *can* be complex
Rel_logGmlogT_eigvals = _gsf.gatesfn_factory(rel_logGmlogT_eigvals)
# init args == (gateset1, gateset2, gateLabel)


def rel_gate_eigenvalues(A, B, mxBasis):
    rel_gate = _np.dot(_np.linalg.inv(B), A) # "relative gate" == target^{-1} * gate
    return _np.linalg.eigvals(rel_gate).astype("complex") #since they generally *can* be complex
Rel_gate_eigenvalues = _gsf.gatesfn_factory(rel_gate_eigenvalues)
# init args == (gateset1, gateset2, gateLabel)


def errgen_and_projections(errgen, mxBasis):
    ret = {}
    egnorm = _np.linalg.norm(errgen.flatten())
    ret['error generator'] = errgen
    proj, scale = \
        _tools.std_errgen_projections( 
            errgen,"hamiltonian",mxBasis.name,mxBasis,return_scale_fctr=True)
        # mxBasis.name because projector dim is not the same as gate dim
    ret['hamiltonian projections'] = proj
    ret['hamiltonian projection power'] =  float(_np.sum(proj**2)/scale**2) / egnorm**2 \
                                           if (abs(scale) > 1e-8 and abs(egnorm) > 1e-8) else 0
      #sum of squared projections of normalized error generator onto normalized projectors
      
    proj, scale = \
        _tools.std_errgen_projections( 
            errgen,"stochastic",mxBasis.name,mxBasis,return_scale_fctr=True)
        # mxBasis.name because projector dim is not the same as gate dim
    ret['stochastic projections'] = proj
    ret['stochastic projection power'] =  float(_np.sum(proj**2)/scale**2) / egnorm**2 \
                                          if (abs(scale) > 1e-8 and abs(egnorm) > 1e-8) else 0
      #sum of squared projections of normalized error generator onto normalized projectors

    proj, scale = \
        _tools.std_errgen_projections( 
            errgen,"affine",mxBasis.name,mxBasis,return_scale_fctr=True)
        # mxBasis.name because projector dim is not the same as gate dim
    ret['affine projections'] = proj
    ret['affine projection power'] = float(_np.sum(proj**2)/scale**2) / egnorm**2 \
                                     if (abs(scale) > 1e-8 and abs(egnorm) > 1e-8) else 0
      #sum of squared projections of normalized error generator onto normalized projectors  
    return ret

def logTiG_and_projections(A, B, mxBasis):
    errgen = _tools.error_generator(A, B, mxBasis, "logTiG")
    return errgen_and_projections(errgen, mxBasis)
LogTiG_and_projections = _gsf.gatesfn_factory(logTiG_and_projections)
# init args == (gateset1, gateset2, gateLabel)

def logGTi_and_projections(A, B, mxBasis):
    errgen = _tools.error_generator(A, B, mxBasis, "logGTi")
    return errgen_and_projections(errgen, mxBasis)
LogGTi_and_projections = _gsf.gatesfn_factory(logGTi_and_projections)
# init args == (gateset1, gateset2, gateLabel)

def logGmlogT_and_projections(A, B, mxBasis):
    errgen = _tools.error_generator(A, B, mxBasis, "logG-logT")
    return errgen_and_projections(errgen, mxBasis)
LogGmlogT_and_projections = _gsf.gatesfn_factory(logGmlogT_and_projections)
# init args == (gateset1, gateset2, gateLabel)



def general_decomposition(gatesetA, gatesetB): # B is target gateset usually but must be "gatsetB" b/c of decorator coding...
    decomp = {}
    gateLabels = list(gatesetA.gates.keys())  # gate labels
    mxBasis = gatesetB.basis # B is usually the target which has a well-defined basis
    
    for gl in gateLabels:
        gate = gatesetA.gates[gl]
        targetGate = gatesetB.gates[gl]

        target_evals = _np.linalg.eigvals(targetGate)
        if _np.any(_np.isclose(target_evals,-1.0)):
            target_logG = _tools.unitary_superoperator_matrix_log(targetGate, mxBasis)        
            logG = _tools.approximate_matrix_log(gate, target_logG)
        else:
            logG = _tools.real_matrix_log(gate, "warn")
            if _np.linalg.norm(logG.imag) > 1e-6:
                _warnings.warn("Truncating imaginary logarithm!")
                logG = _np.real(logG)
                
        decomp[gl + ' log inexactness'] = _np.linalg.norm(_spl.expm(logG)-gate)
    
        hamProjs, hamGens = _tools.std_errgen_projections(
            logG, "hamiltonian", mxBasis.name, mxBasis, return_generators=True)
        norm = _np.linalg.norm(hamProjs)
        decomp[gl + ' axis'] = hamProjs / norm if (norm > 1e-15) else hamProjs
            
        dim = gatesetA.dim
        decomp[gl + ' angle'] = norm * 2.0 / _np.pi
        # Units: hamProjs (and norm) are already in "Hamiltonian-coefficient" units,
        # (see 'std_scale_factor' fn), but because of convention the "angle" is equal
        # to *twice* this coefficient (e.g. a X(pi/2) rotn is exp( i pi/4 X ) ),
        # thus the factor of 2.0 above.
    
        basis_mxs = mxBasis.get_composite_matrices()
        scalings = [ ( _np.linalg.norm(hamGens[i]) / _np.linalg.norm(_tools.hamiltonian_to_lindbladian(mx))
                       if _np.linalg.norm(hamGens[i]) > 1e-10 else 0.0 )
                     for i,mx in enumerate(basis_mxs) ]
          #really want hamProjs[i] * lindbladian_to_hamiltonian(hamGens[i]) but fn doesn't exists (yet)
        hamMx = sum([s*c*bmx for s,c,bmx in zip(scalings,hamProjs,basis_mxs)])
        decomp[gl + ' hamiltonian eigenvalues'] = _np.array(_np.linalg.eigvals(hamMx))

    for gl in gateLabels:
        for gl_other in gateLabels:            
            rotnAngle = decomp[gl + ' angle']
            rotnAngle_other = decomp[gl_other + ' angle']

            if gl == gl_other or abs(rotnAngle) < 1e-4 or abs(rotnAngle_other) < 1e-4:
                decomp[gl + "," + gl_other + " axis angle"] = 10000.0 #sentinel for irrelevant angle
    
            real_dot = _np.clip(
                _np.real(_np.dot(decomp[gl + ' axis'].flatten(),
                                 decomp[gl_other + ' axis'].flatten())),
            -1.0, 1.0)
            angle = _np.arccos( real_dot ) / _np.pi
            decomp[gl + "," + gl_other + " axis angle"] = angle

    return decomp
General_decomposition = _gsf.gatesetfn_factory(general_decomposition)
# init args == (gatesetA, gatesetB)


def average_gateset_infidelity(gatesetA, gatesetB): # B is target gateset usually but must be "gatesetB" b/c of decorator coding...
    from ..extras.rb import rbutils as _rbutils
    return _rbutils.average_gateset_infidelity(gatesetA,gatesetB)
Average_gateset_infidelity = _gsf.gatesetfn_factory(average_gateset_infidelity)
# init args == (gatesetA, gatesetB)


def predicted_rb_number(gatesetA, gatesetB):
    from ..extras.rb import rbutils as _rbutils
    return _rbutils.predicted_RB_number(gatesetA, gatesetB)
Predicted_rb_number = _gsf.gatesetfn_factory(predicted_rb_number)
# init args == (gatesetA, gatesetB)


def vec_fidelity(A, B, mxBasis):
    rhoMx1 = _tools.vec_to_stdmx(A, mxBasis)
    rhoMx2 = _tools.vec_to_stdmx(B, mxBasis)
    return _tools.fidelity(rhoMx1, rhoMx2)
Vec_fidelity = _gsf.vecsfn_factory(vec_fidelity)
# init args == (gateset1, gateset2, label, typ)


def vec_infidelity(A, B, mxBasis):
    rhoMx1 = _tools.vec_to_stdmx(A, mxBasis)
    rhoMx2 = _tools.vec_to_stdmx(B, mxBasis)
    return 1 - _tools.fidelity(rhoMx1, rhoMx2)
Vec_infidelity = _gsf.vecsfn_factory(vec_infidelity)
# init args == (gateset1, gateset2, label, typ)


def vec_tr_diff(A, B, mxBasis): # assume vary gateset1, gateset2 fixed
    rhoMx1 = _tools.vec_to_stdmx(A, mxBasis)
    rhoMx2 = _tools.vec_to_stdmx(B, mxBasis)
    return _tools.tracedist(rhoMx1, rhoMx2)
Vec_tr_diff = _gsf.vecsfn_factory(vec_tr_diff)
# init args == (gateset1, gateset2, label, typ)

def vec_as_stdmx(vec, mxBasis):
    return _tools.vec_to_stdmx(vec, mxBasis)
Vec_as_stdmx = _gsf.vecfn_factory(vec_as_stdmx)

def vec_as_stdmx_eigenvalues(vec, mxBasis):
    mx = _tools.vec_to_stdmx(vec, mxBasis)
    return _np.linalg.eigvals(mx)
Vec_as_stdmx_eigenvalues = _gsf.vecfn_factory(vec_as_stdmx_eigenvalues)


def labeled_data_rows(labels, confidenceRegionInfo, *reportableQtyLists):
    for items in zip(labels, *reportableQtyLists):
        # Python2 friendly unpacking
        label          = items[0]
        reportableQtys = items[1:]
        rowData = [label]
        if confidenceRegionInfo is None:
            rowData.extend([(reportableQty.get_value(), None) for reportableQty in reportableQtys])
        else:
            rowData.extend([reportableQty.get_value_and_err_bar() for reportableQty in reportableQtys])
        yield rowData
