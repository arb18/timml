import numpy as np
import matplotlib.pyplot as plt
import inspect  # Used for storing the input
from .element import Element
from .equation import HeadEquation, MscreenWellEquation
from .trace import timtracelines
from scipy.special import k0, k1


class WellBase(Element):
    def __init__(self, model, xw=0, yw=0, Qw=100.0, rw=0.1, \
                 res=0.0, layers=0, name='WellBase', label=None):
        Element.__init__(self, model, Nparam=1, Nunknowns=0, layers=layers, \
                         name=name, label=label)
        # Defined here and not in Element as other elements can have multiple
        # parameters per layers
        self.Nparam = len(self.layers)
        self.xw = float(xw)
        self.yw = float(yw)
        self.Qw = np.atleast_1d(Qw)
        self.rw = float(rw)
        self.res = float(res)
        self.model.add_element(self)

    def __repr__(self):
        return self.name + ' at ' + str((self.xw, self.yw))

    def initialize(self):
        self.xc = np.array([self.xw + self.rw])
        self.yc = np.array([self.yw])
        self.Ncp = 1
        self.aq = self.model.aq.find_aquifer_data(self.xw, self.yw)
        self.aq.add_element(self)
        self.parameters = np.empty((self.Nparam, 1))
        self.parameters[:, 0] = self.Qw
        self.resfac = self.res / (
        2 * np.pi * self.rw * self.aq.Haq[self.layers])

    def potinf(self, x, y, aq=None):
        if aq is None: aq = self.model.aq.find_aquifer_data(x, y)
        rv = np.zeros((self.Nparam, aq.Naq))
        if aq == self.aq:
            pot = np.zeros(aq.Naq)
            r = np.sqrt((x - self.xw) ** 2 + (y - self.yw) ** 2)
            if r < self.rw: r = self.rw  # If at well, set to at radius
            if aq.ilap:
                pot[0] = np.log(r / self.rw) / (2 * np.pi)
                pot[1:] = -k0(r / aq.lab[1:]) / (2 * np.pi)
            else:
                pot[:] = -k0(r / aq.lab) / (2 * np.pi)
            rv[:] = self.aq.coef[self.layers] * pot
        return rv

    def disvecinf(self, x, y, aq=None):
        if aq is None: aq = self.model.aq.find_aquifer_data(x, y)
        rv = np.zeros((2, self.Nparam, aq.Naq))
        if aq == self.aq:
            qx = np.zeros(aq.Naq)
            qy = np.zeros(aq.Naq)
            rsq = (x - self.xw) ** 2 + (y - self.yw) ** 2
            r = np.sqrt(rsq)
            xminxw = x - self.xw
            yminyw = y - self.yw
            if r < self.rw:
                r = self.rw
                rsq = r ** 2
                xminxw = self.rw
                yminyw = 0.0
            if aq.ilap:
                qx[0] = -1 / (2 * np.pi) * xminxw / rsq
                qy[0] = -1 / (2 * np.pi) * yminyw / rsq
                kone = k1(r / aq.lab[1:])
                qx[1:] = -kone * xminxw / (r * aq.lab[1:]) / (2 * np.pi)
                qy[1:] = -kone * yminyw / (r * aq.lab[1:]) / (2 * np.pi)
            else:
                kone = k1(r / aq.lab)
                qx[:] = -kone * xminxw / (r * aq.lab) / (2 * np.pi)
                qy[:] = -kone * yminyw / (r * aq.lab) / (2 * np.pi)
            rv[0] = self.aq.coef[self.layers] * qx
            rv[1] = self.aq.coef[self.layers] * qy
        return rv

    def headinside(self):
        h = self.model.head(self.xw + self.rw, self.yw, layers=self.layers)
        return h - self.resfac * self.parameters[:, 0]
    
    def discharge(self):
        # returns with the discharge in each layer
        Q = np.zeros(self.aq.Naq)
        Q[self.layers] = self.parameters[:, 0]
        return Q
    
    def stoptrace(self, xyzt, layer, ltype, step, direction):
        terminate = False
        if np.sqrt((xyzt[0] - self.xw) ** 2 + (xyzt[1] - self.yw) ** 2) < (step + self.rw):
            if (ltype == 'a'):
                if (layer == self.layers).any():  # in layer where well is screened
                    if (self.discharge()[layer] > 0 and direction > 0) or (self.discharge()[layer] < 0 and direction < 0):
                        vx, vy, vz = self.model.velocity(*xyzt[:-1])
                        tstep = np.sqrt((xyzt[0] - self.xw) ** 2 + (xyzt[1] - self.yw) ** 2) / np.sqrt(vx ** 2 + vy ** 2)
                        xnew = self.xw
                        ynew = self.yw
                        znew = xyzt[2] + tstep * vz
                        tnew = xyzt[3] + tstep
                        return True, np.array([xnew, ynew, znew, tnew]), str(self)
        return terminate, 0
    
    def capzone(self, hstepmax=10, nt=10, zstart=None, tmax=None, nstepmax=100):
        eps = 1e-1
        angle = np.arange(eps, 2 * np.pi, 2 * np.pi / nt)
        xstart = self.xw + (1 + eps) * self.rw * np.cos(angle)
        ystart = self.yw + (1 + eps) * self.rw * np.sin(angle)
        if zstart is None:
            zstart = self.aq.zaqbot[self.layers[0]] + 0.5 * self.aq.Haq[self.layers[0]]
        zstart = zstart * np.ones(nt)
        xyzt = timtracelines(self.model, xstart, ystart, zstart, -np.abs(hstepmax), \
                             vstepfrac=0.2, tmax=tmax, nstepmax=100, silent='.')
        return xyzt
    
    def plot(self):
        plt.plot(self.xw, self.yw, 'k.')
        
    def plotcapzone(self, hstepmax=10, nt=10, zstart=None, tmax=None, nstepmax=100, color=None):
        xyztlist = self.capzone(hstepmax, nt, zstart, tmax, nstepmax)
        for xyzt in xyztlist:
            plt.plot(xyzt[:, 0], xyzt[:, 1], color=color)
        
        
class Well(WellBase, MscreenWellEquation):
    def __init__(self, model, xw=0, yw=0, Qw=100.0, rw=0.1, \
                 res=0.0, layers=0, label=None):
        self.storeinput(inspect.currentframe())
        WellBase.__init__(self, model, xw, yw, Qw, rw, res, \
                          layers=layers, name='Well', label=label)
        self.Qc = float(Qw)
        if self.Nlayers == 1:
            self.Nunknowns = 0
        else:
            self.Nunknowns = self.Nparam

    def initialize(self):
        WellBase.initialize(self)

    def setparams(self, sol):
        self.parameters[:, 0] = sol


class HeadWell(WellBase, HeadEquation):
    def __init__(self, model, xw=0, yw=0, hw=10.0, rw=0.1, \
                 res=0.0, layers=0, label=None):
        self.storeinput(inspect.currentframe())
        WellBase.__init__(self, model, xw, yw, 0.0, rw, res, \
                          layers=layers, name='HeadWell', label=label)
        self.hc = hw
        self.Nunknowns = self.Nparam

    def initialize(self):
        WellBase.initialize(self)
        self.pc = self.hc * self.aq.T[self.layers]  # Needed in solving

    def setparams(self, sol):
        self.parameters[:, 0] = sol
        