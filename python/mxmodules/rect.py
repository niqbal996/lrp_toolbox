'''
@author: Sebastian Lapuschkin
@author: Gregoire Montavon
@author: Maximilian Kohlbrenner
@maintainer: Sebastian Lapuschkin
@contact: sebastian.lapuschkin@hhi.fraunhofer.de, wojciech.samek@hhi.fraunhofer.de
@date: 14.08.2015
@version: 1.2+
@copyright: Copyright (c)  2015-2017, Sebastian Lapuschkin, Alexander Binder, Gregoire Montavon, Klaus-Robert Mueller, Wojciech Samek
@license : BSD-2-Clause
'''

from .module import Module

import mxnet as mx
from mxnet import nd

# -------------------------------
# Rectification layer
# -------------------------------
class Rect(Module):
    '''
    Rectification Layer
    '''
    def __init__(self, ctx=mx.cpu()):
        '''
        Parameters
        ----------

        ctx:    mxnet.context.Context
                device used for all mxnet.ndarray operations
        '''
        Module.__init__(self)
        self.ctx=ctx

    def forward(self,X):
        self.Y = nd.maximum(0,X)
        return self.Y

    def backward(self,DY):
        return DY*(self.Y!=0)

    def clean(self):
        self.Y = None

    def lrp(self,R,*args,**kwargs):
        # component-wise operations within this layer
        # ->
        # just propagate R further down.
        # makes sure subroutines never get called.
        return R
